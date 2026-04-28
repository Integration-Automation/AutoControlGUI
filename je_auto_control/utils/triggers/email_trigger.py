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
import email
import email.policy
import imaplib
import ssl as ssl_module
import threading
import time
import uuid
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from typing import Any, Callable, Dict, Iterable, List, Optional

from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.run_history.artifact_manager import (
    capture_error_snapshot,
)
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


def _decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except ValueError:
        # UnicodeDecodeError is a subclass of ValueError; one entry is enough.
        return str(value)


def _extract_text_body(msg) -> str:
    """Return the first text/plain part as a string, falling back to the body."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" \
                    and "attachment" not in (part.get("Content-Disposition") or ""):
                try:
                    return part.get_content().strip()
                except (LookupError, ValueError):
                    continue
        return ""
    try:
        return (msg.get_content() or "").strip()
    except (LookupError, ValueError):
        return ""


def _build_payload(uid: str, msg) -> Dict[str, Any]:
    return {
        "email.uid": uid,
        "email.from": _decode_header_value(msg.get("From")),
        "email.to": _decode_header_value(msg.get("To")),
        "email.subject": _decode_header_value(msg.get("Subject")),
        "email.message_id": msg.get("Message-ID", ""),
        "email.date": msg.get("Date", ""),
        "email.body": _extract_text_body(msg),
    }


def _connect(trigger: EmailTrigger) -> imaplib.IMAP4:
    """Open and authenticate against the IMAP server."""
    context = ssl_module.create_default_context()
    # Pin a modern TLS floor; create_default_context already does this on
    # 3.10+, but stating it explicitly satisfies python:S4423.
    context.minimum_version = ssl_module.TLSVersion.TLSv1_2
    if trigger.use_ssl:
        client = imaplib.IMAP4_SSL(trigger.host, trigger.port,
                                   ssl_context=context)
    else:
        client = imaplib.IMAP4(trigger.host, trigger.port)
    client.login(trigger.username, trigger.password)
    return client


def _search_uids(client: imaplib.IMAP4, criteria: str) -> List[bytes]:
    typ, data = client.uid("SEARCH", None, criteria or "UNSEEN")
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _fetch_message(client: imaplib.IMAP4, uid: bytes):
    typ, data = client.uid("FETCH", uid, "(RFC822)")
    if typ != "OK" or not data or data[0] is None:
        return None
    raw = data[0][1] if isinstance(data[0], tuple) else data[0]
    if not isinstance(raw, (bytes, bytearray)):
        return None
    return email.message_from_bytes(bytes(raw), policy=email.policy.default)


def _mark_seen(client: imaplib.IMAP4, uid: bytes) -> None:
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
        if executor is None:
            self._executor = self._default_executor
        else:
            self._executor = executor

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
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="AutoControlEmailTrigger",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None

    def poll_once(self) -> int:
        """Run exactly one polling pass; return total messages fired."""
        return self._poll_pass()

    def _run(self) -> None:
        last_check: Dict[str, float] = {}
        while not self._stop.is_set():
            now = time.monotonic()
            for trigger in self.list_triggers():
                if not trigger.enabled:
                    continue
                if now - last_check.get(trigger.trigger_id, 0.0) \
                        < trigger.poll_seconds:
                    continue
                self._poll_one(trigger)
                last_check[trigger.trigger_id] = now
            self._stop.wait(1.0)

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
            typ, _ = client.select(trigger.mailbox, readonly=False)
            if typ != "OK":
                trigger.last_error = f"select {trigger.mailbox} failed"
                return 0
            for uid in self._iter_unprocessed_uids(client, trigger):
                fired += self._fire_for_uid(client, trigger, uid)
        finally:
            try:
                client.logout()
            except (imaplib.IMAP4.error, OSError):
                pass
        return fired

    def _iter_unprocessed_uids(self, client: imaplib.IMAP4,
                               trigger: EmailTrigger) -> Iterable[bytes]:
        for uid in _search_uids(client, trigger.search_criteria):
            uid_str = uid.decode("ascii", errors="replace")
            if uid_str in trigger._seen_uids:
                continue
            yield uid

    def _record_connect_error(self, trigger: EmailTrigger,
                              error: Exception) -> None:
        trigger.last_error = repr(error)
        autocontrol_logger.error("imap %s connect failed: %r",
                                 trigger.trigger_id, error)

    def _fire_for_uid(self, client: imaplib.IMAP4,
                      trigger: EmailTrigger, uid: bytes) -> int:
        msg = _fetch_message(client, uid)
        if msg is None:
            return 0
        uid_str = uid.decode("ascii", errors="replace")
        payload = _build_payload(uid_str, msg)
        try:
            self._execute_with_history(trigger, payload)
        except (OSError, ValueError, RuntimeError) as error:
            trigger.last_error = repr(error)
            autocontrol_logger.error("imap %s fire failed: %r",
                                     trigger.trigger_id, error)
        else:
            trigger.last_error = None
        trigger._seen_uids.add(uid_str)
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
                actions = read_action_json(trigger.script_path)
                self._executor(actions, payload)
            except (OSError, ValueError, RuntimeError) as error:
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
