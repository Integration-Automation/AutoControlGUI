"""IMAP poll trigger: fire a script when a matching email arrives.

Each watcher entry connects to an IMAP mailbox on a configurable
schedule and runs an action JSON file once per matching message. When
a message fires, the executor receives the parsed metadata as variables
(``email.from``, ``email.subject``, ``email.body`` …) so the script can
react to the contents through ``${email.subject}`` placeholders.

Polling — not IDLE — is used so the implementation stays standard-
library only and survives flaky network paths. Messages are matched
once: by default the watcher marks the message as ``\\Seen`` after a
successful fire so the same email is not handled twice across
restarts.
"""
import base64
import email
import email.policy
import re
import imaplib
import ssl as ssl_module
import threading
import time
import uuid
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from typing import Any, Callable, Dict, Iterable, List, Optional

from je_auto_control.utils.json.json_file import read_executable_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.run_history.artifact_manager import (
    capture_error_snapshot,
)
from je_auto_control.utils.run_history.run_outcome import run_counting_failures
from je_auto_control.utils.run_history.history_store import (
    SOURCE_TRIGGER, STATUS_ERROR, STATUS_OK, default_history_store,
)


_DEFAULT_POLL_SECONDS = 60.0
_MIN_POLL_SECONDS = 5.0
_DEFAULT_PORT_SSL = 993
_DEFAULT_PORT_PLAIN = 143


@dataclass
class EmailTrigger:
    """One IMAP mailbox → action-script binding."""
    trigger_id: str
    host: str
    username: str
    password: str
    script_path: str
    port: int = _DEFAULT_PORT_SSL
    use_ssl: bool = True
    mailbox: str = "INBOX"
    search_criteria: str = "UNSEEN"
    mark_seen: bool = True
    poll_seconds: float = _DEFAULT_POLL_SECONDS
    enabled: bool = True
    fired: int = 0
    last_error: Optional[str] = None
    _seen_uids: set = field(default_factory=set, repr=False)
    _inflight: set = field(default_factory=set, repr=False)
    _uidvalidity: Optional[str] = field(default=None, repr=False)


def _decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except (ValueError, LookupError):
        # UnicodeDecodeError is a subclass of ValueError. A header naming an
        # unknown charset (e.g. =?not-a-charset?B?..?=) raises LookupError from
        # the codec lookup — uncaught it would poison the whole mailbox poll.
        return str(value)


def _part_text(part) -> Optional[str]:
    """A text part's content, or ``None`` when its bytes cannot be read.

    A charset Python does not know (``unknown-8bit``, ``x-user-defined``,
    common on mailing lists) raised ``LookupError`` and the body was dropped;
    the raw bytes are decoded as UTF-8 with replacement instead.
    """
    try:
        return (part.get_content() or "").strip()
    except LookupError:
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            return None
        return payload.decode("utf-8", errors="replace").strip()
    except ValueError:
        return None


def _extract_text_body(msg) -> str:
    """Return the first text/plain part as a string, falling back to the body."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" \
                    and "attachment" not in (part.get("Content-Disposition") or ""):
                text = _part_text(part)
                if text is not None:
                    return text
        return ""
    return _part_text(msg) or ""


def _header(msg, name: str) -> str:
    """A header's decoded value, or its raw text when it does not parse.

    ``email.policy.default`` parses a header when it is read, and a
    malformed address (``From: <"``) raises IndexError, HeaderParseError or
    AttributeError from inside the email package -- which escaped the poll
    and blocked the mailbox on that message for good.
    """
    try:
        value = msg.get(name)
    except Exception:  # noqa: BLE001  # reason: the email package's parse errors have no common base; fall back to the raw header
        value = next((str(raw) for key, raw in msg.raw_items()
                      if key.lower() == name.lower()), None)
    return _decode_header_value(value)


def _build_payload(uid: str, msg) -> Dict[str, Any]:
    return {
        "email.uid": uid,
        "email.from": _header(msg, "From"),
        "email.to": _header(msg, "To"),
        "email.subject": _header(msg, "Subject"),
        "email.message_id": _header(msg, "Message-ID"),
        "email.date": _header(msg, "Date"),
        "email.body": _extract_text_body(msg),
    }


#: Seconds any one IMAP connect or command may block.
_IMAP_TIMEOUT_S = 30.0


def _connect(trigger: EmailTrigger) -> imaplib.IMAP4:
    """Open and authenticate against the IMAP server."""
    context = ssl_module.create_default_context()
    # Pin a modern TLS floor; create_default_context already does this on
    # 3.10+, but stating it explicitly satisfies python:S4423.
    context.minimum_version = ssl_module.TLSVersion.TLSv1_2
    client: imaplib.IMAP4
    # Without a timeout a server that accepts and never greets hung this
    # watcher's thread for good: stop() gave up on it and start() added
    # another.
    if trigger.use_ssl:
        client = imaplib.IMAP4_SSL(trigger.host, trigger.port,
                                   ssl_context=context, timeout=_IMAP_TIMEOUT_S)
    else:
        client = imaplib.IMAP4(trigger.host, trigger.port, timeout=_IMAP_TIMEOUT_S)
    client.login(trigger.username, trigger.password)
    return client


def _search_uids(client: imaplib.IMAP4, criteria: str) -> List[str]:
    """Return the matching message UIDs.

    ``imaplib`` accepts the UID as either ``str`` or ``bytes`` and encodes
    ASCII either way; the searched-for UIDs arrive as bytes and are decoded
    here so every helper below takes one type.
    """
    typ, data = client.uid("SEARCH", criteria or "UNSEEN")
    if typ != "OK" or not data or not data[0]:
        return []
    return [chunk.decode("ascii", "replace") for chunk in data[0].split()]


def _fetch_message(client: imaplib.IMAP4, uid: str):
    # BODY.PEEK[]: a plain RFC822 fetch sets \Seen on the server (RFC 3501),
    # so messages were marked read with mark_seen=False, and before the
    # script had run -- one lost for good if the process died mid-run.
    typ, data = client.uid("FETCH", uid, "(BODY.PEEK[])")
    if typ != "OK" or not data or data[0] is None:
        return None
    raw = data[0][1] if isinstance(data[0], tuple) else data[0]
    if not isinstance(raw, (bytes, bytearray)):
        return None
    return email.message_from_bytes(bytes(raw), policy=email.policy.default)


def _quote_mailbox(name: str) -> str:
    """``name`` as an IMAP quoted string.

    imaplib sends ``select``'s argument as-is, so ``Sent Items`` went out as
    two atoms (``SELECT Sent Items``), a BAD command; ``[Gmail]/All Mail``
    likewise.
    """
    if len(name) >= 2 and name.startswith('"') and name.endswith('"'):
        return name
    escaped = _modified_utf7(name).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


#: An ASCII name that already holds modified UTF-7 shifts (``&-``, ``&ZeVnLIqe-``).
_ENCODED_MAILBOX = re.compile(r"&[A-Za-z0-9+,]*-")


def _modified_utf7(name: str) -> str:
    """``name`` in IMAP's modified UTF-7 (RFC 3501 5.1.3), unless it already is.

    ``已處理`` raised UnicodeEncodeError before any command was sent, and
    ``R&D`` went out as ``R&D`` where the protocol needs ``R&-D``.
    """
    if name.isascii() and _ENCODED_MAILBOX.search(name):
        return name
    out: List[str] = []
    pending: List[str] = []

    def flush() -> None:
        if pending:
            encoded = base64.b64encode("".join(pending).encode("utf-16-be")).decode("ascii")
            out.append("&" + encoded.rstrip("=").replace("/", ",") + "-")
            pending.clear()

    for char in name:
        if 0x20 <= ord(char) <= 0x7E:
            flush()
            out.append("&-" if char == "&" else char)
        else:
            pending.append(char)
    flush()
    return "".join(out)


def _mark_seen(client: imaplib.IMAP4, uid: str) -> None:
    try:
        client.uid("STORE", uid, "+FLAGS", "(\\Seen)")
    except imaplib.IMAP4.error as error:
        autocontrol_logger.warning("imap mark seen failed: %r", error)


class EmailTriggerWatcher:
    """Polls registered IMAP triggers from a single background thread."""

    def __init__(self,
                 executor: Optional[Callable[[list, Dict[str, Any]], Any]] = None,
                 ) -> None:
        self._lock = threading.RLock()
        self._fire_lock = threading.Lock()
        self._triggers: Dict[str, EmailTrigger] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._executor: Callable[[list, Dict[str, Any]], Any] = (
            self._default_executor if executor is None else executor
        )

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def add(self,
            host: str, username: str, password: str, script_path: str,
            *,
            port: Optional[int] = None,
            use_ssl: bool = True,
            mailbox: str = "INBOX",
            search_criteria: str = "UNSEEN",
            mark_seen: bool = True,
            poll_seconds: float = _DEFAULT_POLL_SECONDS) -> EmailTrigger:
        """Register a new IMAP trigger."""
        if not host or not username or not script_path:
            raise ValueError(
                "host, username, and script_path are required",
            )
        if port is not None:
            resolved_port = int(port)
        elif use_ssl:
            resolved_port = _DEFAULT_PORT_SSL
        else:
            resolved_port = _DEFAULT_PORT_PLAIN
        trigger = EmailTrigger(
            trigger_id=uuid.uuid4().hex[:8],
            host=str(host), username=str(username), password=str(password),
            script_path=str(script_path),
            port=resolved_port, use_ssl=bool(use_ssl),
            mailbox=str(mailbox or "INBOX"),
            search_criteria=str(search_criteria or "UNSEEN"),
            mark_seen=bool(mark_seen),
            poll_seconds=max(_MIN_POLL_SECONDS, float(poll_seconds)),
        )
        with self._lock:
            self._triggers[trigger.trigger_id] = trigger
        return trigger

    def remove(self, trigger_id: str) -> bool:
        with self._lock:
            return self._triggers.pop(trigger_id, None) is not None

    def list_triggers(self) -> List[EmailTrigger]:
        with self._lock:
            return list(self._triggers.values())

    def set_enabled(self, trigger_id: str, enabled: bool) -> bool:
        with self._lock:
            trigger = self._triggers.get(trigger_id)
            if trigger is None:
                return False
            trigger.enabled = bool(enabled)
            return True

    def start(self) -> None:
        with self._lock:
            if self.is_running:
                return
            # A fresh event per run, never clear() on the old one: a thread that
            # outlived stop()'s join would see it cleared and keep running.
            self._stop = threading.Event()
            self._thread = threading.Thread(
                target=self._run, args=(self._stop,), name="AutoControlEmailTrigger",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop polling; under start()'s lock so it never joins an unstarted thread."""
        with self._lock:
            self._stop.set()
            thread = self._thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=timeout)
            self._thread = None

    def poll_once(self) -> int:
        """Run exactly one polling pass; return total messages fired."""
        return self._poll_pass()

    def _run(self, stop: threading.Event) -> None:
        last_check: Dict[str, float] = {}
        while not stop.is_set():
            now = time.monotonic()
            for trigger in self.list_triggers():
                if not trigger.enabled:
                    continue
                if now - last_check.get(trigger.trigger_id, 0.0) \
                        < trigger.poll_seconds:
                    continue
                # 任何一個 trigger 都不該讓輪詢執行緒陣亡。
                # Belt and braces: _poll_one now records its own IMAP errors,
                # but nothing a single trigger does may stop the loop and take
                # every other email trigger down with it.
                try:
                    self._poll_one(trigger)
                except Exception as error:  # noqa: BLE001  # reason: see above
                    trigger.last_error = repr(error)
                    autocontrol_logger.error(
                        "email trigger %s poll failed: %r",
                        trigger.trigger_id, error, exc_info=True,
                    )
                last_check[trigger.trigger_id] = now
            stop.wait(1.0)

    def _poll_pass(self) -> int:
        fired = 0
        for trigger in self.list_triggers():
            if trigger.enabled:
                fired += self._poll_one(trigger)
        return fired

    def _poll_one(self, trigger: EmailTrigger) -> int:
        try:
            client = _connect(trigger)
        except (OSError, imaplib.IMAP4.error) as error:
            self._record_connect_error(trigger, error)
            return 0
        fired = 0
        try:
            typ, _ = client.select(_quote_mailbox(trigger.mailbox), readonly=False)
            if typ != "OK":
                trigger.last_error = f"select {trigger.mailbox} failed"
                return 0
            self._check_uidvalidity(client, trigger)
            for uid in self._iter_unprocessed_uids(client, trigger):
                fired += self._fire_claimed(client, trigger, uid)
        # 只有 _connect 有防護，select / search / fetch 沒有。連線在指令
        # 途中斷掉時 imaplib 會拋 IMAP4.abort，逸出 _run 後直接殺掉輪詢
        # 執行緒——而這個模組的文件正說它能撐過不穩定的網路。
        # Only _connect was guarded. imaplib raises IMAP4.abort when the
        # connection drops mid-command (routine on a flaky network, which this
        # module's docstring claims to survive); it escaped _run and killed the
        # polling thread, silently stopping every email trigger for good.
        except (OSError, imaplib.IMAP4.error) as error:
            self._record_connect_error(trigger, error)
            return 0
        finally:
            try:
                client.logout()
            except (imaplib.IMAP4.error, OSError):
                pass
        return fired

    def _iter_unprocessed_uids(self, client: imaplib.IMAP4,
                               trigger: EmailTrigger) -> Iterable[str]:
        for uid in _search_uids(client, trigger.search_criteria):
            if self._claim(trigger, uid):
                yield uid

    def _claim(self, trigger: EmailTrigger, uid: str) -> bool:
        """Take ``uid`` for this poll, atomically; ``False`` when seen or taken.

        The check came before the fire and the mark after it, so two polls
        running together (the watcher and AC_email_trigger_poll_once) both
        fired the same message.
        """
        with self._lock:
            if uid in trigger._seen_uids or uid in trigger._inflight:
                return False
            trigger._inflight.add(uid)
            return True

    def _fire_claimed(self, client: imaplib.IMAP4, trigger: EmailTrigger, uid: str) -> int:
        try:
            return self._fire_for_uid(client, trigger, uid)
        finally:
            with self._lock:
                trigger._inflight.discard(uid)

    def _check_uidvalidity(self, client: imaplib.IMAP4, trigger: EmailTrigger) -> None:
        """Forget the seen UIDs when the mailbox's UIDVALIDITY changes.

        A new UIDVALIDITY means UIDs were reassigned, and a new message that
        reused an old UID was skipped for good.
        """
        _typ, data = client.response("UIDVALIDITY")
        value = data[0] if data else None
        if isinstance(value, (bytes, bytearray)):
            value = bytes(value).decode("ascii", errors="replace")
        if value is None:
            return
        with self._lock:
            if trigger._uidvalidity is not None and value != trigger._uidvalidity:
                trigger._seen_uids.clear()
            trigger._uidvalidity = str(value)

    def _record_connect_error(self, trigger: EmailTrigger,
                              error: Exception) -> None:
        trigger.last_error = repr(error)
        autocontrol_logger.error("imap %s connect failed: %r",
                                 trigger.trigger_id, error)

    def _fire_for_uid(self, client: imaplib.IMAP4,
                      trigger: EmailTrigger, uid: str) -> int:
        msg = _fetch_message(client, uid)
        if msg is None:
            return 0
        try:
            payload = _build_payload(uid, msg)
        except Exception as error:  # noqa: BLE001  # reason: a message the email package cannot read is skipped, not retried forever
            trigger.last_error = repr(error)
            autocontrol_logger.error("imap %s unreadable message %s: %r",
                                     trigger.trigger_id, uid, error)
            trigger._seen_uids.add(uid)
            return 0
        # A missing/renamed script raises AutoControlJsonActionException (an
        # AutoControlException). Missing the base here let it escape *before*
        # the uid was marked seen below, so the same message re-fired every
        # poll forever. Catch the whole family: record the failure and still
        # mark the uid processed. The same holds for any other error a script
        # or custom executor raises (KeyError, TypeError...): a narrower tuple
        # re-fired the message on every poll.
        try:
            self._execute_with_history(trigger, payload)
        except Exception as error:  # noqa: BLE001  # reason: recorded; the uid must still be marked seen
            trigger.last_error = repr(error)
            autocontrol_logger.error("imap %s fire failed: %r",
                                     trigger.trigger_id, error)
        else:
            trigger.last_error = None
        trigger._seen_uids.add(uid)
        if trigger.mark_seen:
            _mark_seen(client, uid)
        return 1

    def _execute_with_history(self, trigger: EmailTrigger,
                              payload: Dict[str, Any]) -> None:
        with self._fire_lock:
            run_id = default_history_store.start_run(
                SOURCE_TRIGGER, f"email:{trigger.trigger_id}",
                trigger.script_path,
            )
            status = STATUS_OK
            error_text: Optional[str] = None
            try:
                actions = read_executable_action_json(trigger.script_path)
                run_counting_failures(lambda: self._executor(actions, payload))
            # Any failure is recorded as STATUS_ERROR -- not a bogus
            # STATUS_OK from the finally below -- before re-raising.
            except Exception as error:  # noqa: BLE001  # reason: re-raised
                status = STATUS_ERROR
                error_text = repr(error)
                raise
            finally:
                artifact = (capture_error_snapshot(run_id)
                            if status == STATUS_ERROR else None)
                default_history_store.finish_run(
                    run_id, status, error_text, artifact_path=artifact,
                )
                trigger.fired += 1

    @staticmethod
    def _default_executor(actions: list, variables: Dict[str, Any]) -> Any:
        from je_auto_control.utils.executor.action_executor import (
            execute_action_with_vars,
        )
        return execute_action_with_vars(actions, variables)


default_email_trigger_watcher = EmailTriggerWatcher()
