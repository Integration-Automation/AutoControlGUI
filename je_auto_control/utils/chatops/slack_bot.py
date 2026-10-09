"""Slack adapter for :class:`CommandRouter`.

Polling-only by default — no need for a public webhook URL or signing
secret. Reads the last N messages from one channel via
``conversations.history``, hands every new message to the router, and
posts replies with ``chat.postMessage``. Suitable for internal
infrastructure where the bot lives on a private network and pulls
work rather than receiving pushes.

A command named in ``background_commands`` (``/run`` by default) executes on
a worker thread and is answered when it ends, so the poll loop keeps reading
while it lasts -- that is what lets a ``/stop`` posted to the channel reach
the bot's own run. One such command runs at a time per bot; a second is
refused with a reply. Every other command is dispatched and answered on the
poll thread, as before.

Three pieces of state are tracked per channel:

* ``last_seen_ts`` — the Slack timestamp of the most-recent message we
  have already routed; persisted across ``poll_once`` calls;
* ``bot_user_id`` — the bot's own user id, looked up lazily so we
  don't loop on our own replies;
* ``error_backoff_s`` — multiplicative back-off on consecutive
  failures, capped so the poller stays responsive.
"""
from __future__ import annotations

import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

from je_auto_control.utils.chatops.handlers import chatops_run_id
from je_auto_control.utils.chatops.router import (
    ChatOpsError, CommandResult, CommandRouter,
)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.run_control import StopToken, stoppable_run
from je_auto_control.utils.http_client.http_client import build_call, perform_call
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_SLACK_API = "https://slack.com/api"
_HTTP_TIMEOUT = 15.0
_MIN_POLL_INTERVAL = 1.0
_MAX_PAGES = 20  # 1000 messages per poll
_MAX_BACKOFF = 60.0
#: How long the poll thread waits for a started command to be listed as a run.
_START_WAIT = 10.0
#: How long :meth:`SlackBot.stop` waits for the running command by default.
_JOIN_TIMEOUT = 10.0
#: What the name of every worker thread begins with.
_WORKER_PREFIX = "chatops-slack-"
#: What a dispatch may fail with beyond what the router already contains:
#: defence in depth, as wide as the router's own boundary. An ImportError
#: from a handler's lazy import ended ``run_forever`` for good.
_ROUTE_ERRORS = (RuntimeError, ValueError, TypeError, LookupError, AttributeError,
                 ImportError, ArithmeticError, OSError, AutoControlException)


class SlackError(AutoControlException, RuntimeError):
    """Raised when the Slack API returns ``ok: false`` or HTTP fails."""


@dataclass
class SlackBot:
    """Polling Slack adapter wrapped around a :class:`CommandRouter`.

    ``background_commands`` names the commands that run on a worker thread
    (case-insensitive, without the prefix); see the module docstring.
    """

    token: str
    channel_id: str
    router: CommandRouter
    poll_interval_s: float = 5.0
    last_seen_ts: Optional[str] = None
    _bot_user_id: Optional[str] = None
    _stop: threading.Event = field(default_factory=threading.Event)
    background_commands: FrozenSet[str] = frozenset({"run"})
    # The one background command in progress: its thread and its stop token.
    _worker: Optional[threading.Thread] = field(default=None, init=False, repr=False)
    _run_token: Optional[StopToken] = field(default=None, init=False, repr=False)
    _state_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False)
    # Held while one message is dispatched and answered, and by the worker
    # while it posts its reply: the answer to a /stop is posted before the
    # "stopped" reply of the run it ended.
    _turn: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.token or not self.token.startswith("xox"):
            raise SlackError("Slack token must start with 'xox' (bot token)")
        if not self.channel_id:
            raise SlackError("channel_id must be a non-empty string")
        if self.poll_interval_s < _MIN_POLL_INTERVAL:
            raise SlackError(
                f"poll_interval_s must be >= {_MIN_POLL_INTERVAL}",
            )
        if isinstance(self.background_commands, str):
            raise SlackError("background_commands must be a set of command names")
        self.background_commands = frozenset(
            str(name).strip().lower() for name in self.background_commands)

    # --- polling -------------------------------------------------

    def poll_once(self) -> int:
        """Pull new messages, dispatch each through the router. Returns count.

        A background command counts once it is started (or refused); the call
        returns without waiting for it.
        """
        messages = self._fetch_messages()
        if not messages:
            return 0
        # Slack returns newest-first; reverse so we route in chronological order.
        ordered = list(reversed(messages))
        dispatched = 0
        for msg in ordered:
            ts = str(msg.get("ts") or "")
            if not ts:
                continue
            # Commit progress *before* running the command. A command's side
            # effects (running a script, taking a screenshot) happen exactly
            # once inside _route_one; if the handler or the reply post then
            # fails, the next poll must not re-execute it. Advancing last_seen_ts
            # here (Slack's `oldest` is exclusive) guarantees at-most-once.
            self.last_seen_ts = max(self.last_seen_ts or "0", ts)
            if self._is_self(msg):
                continue
            text = str(msg.get("text") or "")
            if self._handle(text, msg):
                dispatched += 1
        return dispatched

    def run_forever(self, *, max_iterations: Optional[int] = None) -> None:
        """Poll on a loop until :meth:`stop` is called."""
        # A fresh event per call, never clear() on the old one: a loop still
        # inside poll_once() when stop() was called would see it cleared by
        # the next run_forever() and keep polling beside it.
        stop = self._stop = threading.Event()
        backoff = 0.0
        iteration = 0
        while not stop.is_set():
            try:
                self.poll_once()
                backoff = 0.0
            except SlackError as error:
                autocontrol_logger.warning(f"chatops slack poll: {error}")
                backoff = min(_MAX_BACKOFF, max(backoff * 2, 2.0))
            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                return
            stop.wait(self.poll_interval_s + backoff)

    def stop(self, timeout: float = _JOIN_TIMEOUT) -> bool:
        """End the poll loop, stop the running background command and join it.

        The command is asked to stop the way ``/stop`` asks, and its worker is
        waited for up to ``timeout`` seconds; it still posts its reply. Returns
        whether no worker is left. ``False`` means the command is inside a
        call that cannot be interrupted (the worker is a daemon thread and
        ends with the process), or that this was called from a command
        handler, which holds the turn the worker needs to post its reply.
        Until :meth:`run_forever` is called again a background command is
        refused rather than started.
        """
        self._stop.set()
        with self._state_lock:
            worker, token = self._worker, self._run_token
        if worker is None or not worker.is_alive():
            return True
        if token is not None:
            token.stop("the bot was stopped")
        return self._join(worker, timeout)

    def wait_idle(self, timeout: float = _JOIN_TIMEOUT) -> bool:
        """Wait up to ``timeout`` seconds for the running background command to end.

        Nothing is stopped. Returns whether the bot has no command running.
        """
        with self._state_lock:
            worker = self._worker
        if worker is None or not worker.is_alive():
            return True
        return self._join(worker, timeout)

    @property
    def running_run_id(self) -> Optional[str]:
        """The run id of the background command in progress, or ``None``."""
        with self._state_lock:
            if self._worker is None or not self._worker.is_alive():
                return None
            return self._run_token.run_id if self._run_token is not None else None

    @staticmethod
    def _join(worker: threading.Thread, timeout: float) -> bool:
        """Join ``worker`` for at most ``timeout`` seconds; whether it has ended."""
        if worker is threading.current_thread():
            return False  # called from the command itself: it cannot wait for itself
        worker.join(max(0.0, float(timeout)))
        if worker.is_alive():
            autocontrol_logger.warning(
                f"chatops slack: {worker.name} is still running after {timeout}s")
            return False
        return True

    # --- routing -------------------------------------------------

    def _handle(self, text: str, message: Dict[str, Any]) -> bool:
        """Dispatch one message; whether it was a command."""
        with self._turn:
            argv = self._background_argv(text)
            if argv is None:
                return self._route_one(text, message) is not None
            return self._start_background(argv, text, message)

    def _context(self, message: Dict[str, Any]) -> Dict[str, Any]:
        return {"slack_user": message.get("user"), "slack_ts": message.get("ts"),
                "slack_channel": self.channel_id}

    def _route_one(self, text: str,
                   message: Dict[str, Any]) -> Optional[CommandResult]:
        # The router already converts handler failures into CommandResults;
        # this is defence in depth so a framework error surfaces as a chat
        # reply rather than escaping poll_once and stopping run_forever.
        try:
            result = self.router.dispatch(text, context=self._context(message))
        except _ROUTE_ERRORS as error:
            self.post_message(f"router error: {error}")
            return None
        if result is None:
            return None
        self.post_message(result.text, thread_ts=str(message.get("ts") or ""))
        return result

    # --- background commands -------------------------------------

    def _background_argv(self, text: str) -> Optional[List[str]]:
        """The parsed command when ``text`` is one that runs in the background."""
        try:
            argv = self.router.parse(text)
        except ChatOpsError:
            return None  # the synchronous path answers with the parse error
        if not argv or argv[0].lower() not in self.background_commands:
            return None
        return argv

    def _start_background(self, argv: List[str], text: str,
                          message: Dict[str, Any]) -> bool:
        """Start ``text`` on a worker, or say why not; always ``True`` (it was a command)."""
        name = argv[0].lower()
        listed = threading.Event()
        refusal = ""
        with self._state_lock:
            if self._worker is not None and self._worker.is_alive():
                running = self._run_token.run_id if self._run_token is not None else "?"
                refusal = (f"{name}: already running ({running}); wait for it to end "
                           f"or {self.router.prefix}stop it first.")
            elif self._stop.is_set():
                refusal = f"{name}: the bot is stopping; not started."
            else:
                token = StopToken(chatops_run_id(argv[1] if len(argv) > 1 else name))
                self._run_token = token
                self._worker = threading.Thread(
                    target=self._run_background, args=(text, message, token, listed),
                    name=f"{_WORKER_PREFIX}{token.run_id}", daemon=True)
                self._worker.start()
        if refusal:
            self.post_message(refusal, thread_ts=str(message.get("ts") or ""))
            return True
        # The next message may be the /stop for this run: read it only once
        # the run is listed (or has already ended).
        listed.wait(_START_WAIT)
        return True

    def _run_background(self, text: str, message: Dict[str, Any],
                        token: StopToken, listed: threading.Event) -> None:
        """Worker thread: run one command as a stoppable run, then post its reply."""
        try:
            reply = self._dispatch_stoppable(text, message, token, listed)
        finally:
            listed.set()
        if not reply:
            return
        with self._turn:
            try:
                self.post_message(reply, thread_ts=str(message.get("ts") or ""))
            except SlackError as error:
                # Nobody to raise to: the command has run and is not retried.
                autocontrol_logger.warning(
                    f"chatops slack: reply of {token.run_id} not posted: {error}")

    def _dispatch_stoppable(self, text: str, message: Dict[str, Any],
                            token: StopToken, listed: threading.Event) -> str:
        """Dispatch ``text`` inside the run named by ``token``; the reply text.

        ``/run`` joins the run it finds itself in, so ``token`` is the one
        ``/stop`` and :meth:`stop` address, from before the script is opened.
        """
        try:
            with stoppable_run(token=token):
                listed.set()
                result = self.router.dispatch(text, context=self._context(message))
        except _ROUTE_ERRORS as error:
            return f"router error: {error}"
        return result.text if result is not None else ""

    # --- HTTP wrappers -------------------------------------------

    def post_message(self, text: str,
                     *, thread_ts: str = "") -> Dict[str, Any]:
        payload: Dict[str, Any] = {"channel": self.channel_id, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return self._api_post("chat.postMessage", payload)

    def _fetch_messages(self) -> list:
        """Every message since ``last_seen_ts``, newest first, across pages.

        One page of 50 was read and ``last_seen_ts`` then moved past the
        newest, so older messages beyond the first page were never routed.
        """
        params: Dict[str, Any] = {
            "channel": self.channel_id,
            "limit": 50,
        }
        if self.last_seen_ts:
            params["oldest"] = self.last_seen_ts
        messages: list = []
        for _ in range(_MAX_PAGES):
            body = self._api_get("conversations.history", params)
            messages.extend(message for message in body.get("messages") or []
                            if isinstance(message, dict))
            cursor = (body.get("response_metadata") or {}).get("next_cursor")
            if not body.get("has_more") or not cursor:
                break
            params["cursor"] = cursor
        return messages

    def _is_self(self, message: Dict[str, Any]) -> bool:
        if message.get("subtype") == "bot_message":
            return True
        user = message.get("user")
        if not user:
            return False
        if self._bot_user_id is None:
            self._bot_user_id = self._lookup_bot_user_id()
        return user == self._bot_user_id

    def _lookup_bot_user_id(self) -> Optional[str]:
        try:
            body = self._api_get("auth.test", {})
        except SlackError:
            return None
        return body.get("user_id")

    def _api_get(self, method: str,
                 params: Dict[str, Any]) -> Dict[str, Any]:
        query = urllib.parse.urlencode(params)
        url = f"{_SLACK_API}/{method}?{query}"
        return self._request(url, method="GET")

    def _api_post(self, method: str,
                  payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(
            f"{_SLACK_API}/{method}", method="POST",
            payload=payload,
        )

    def _request(self, url: str, *, method: str,
                 payload: Optional[Dict[str, Any]] = None,
                 ) -> Dict[str, Any]:
        if not url.startswith("https://slack.com/api/"):
            raise SlackError(f"refusing to call non-Slack URL: {url}")
        # Through http_client, so the egress policy applies to Slack too; a
        # Slack API call never redirects, so a 3xx is an error, not followed.
        call = build_call(url, method, headers={"Authorization": f"Bearer {self.token}"},
                          json_body=payload, timeout=_HTTP_TIMEOUT)
        call["follow_redirects"] = False
        try:
            response = perform_call(call)
        except (OSError, ValueError) as error:  # URLError, EgressBlocked
            raise SlackError(f"HTTP failure: {error}") from error
        body = response["json"]
        if not isinstance(body, dict):
            # A list or string body raised AttributeError, which run_forever
            # does not catch: one bad reply ended the poll loop for good.
            raise SlackError(f"Slack {url} returned HTTP {response['status']} "
                             "without a JSON object")
        if not body.get("ok"):
            raise SlackError(
                f"Slack {url} returned {body.get('error', 'unknown')}",
            )
        return body


def make_default_slack_bot(*, token: str, channel_id: str,
                           script_root: Optional[str] = None,
                           ) -> SlackBot:
    """Wire a :class:`SlackBot` with the default command set in one call."""
    from je_auto_control.utils.chatops.handlers import (
        register_default_commands,
    )
    router = CommandRouter()
    register_default_commands(router)
    bot = SlackBot(token=token, channel_id=channel_id, router=router)
    if script_root is not None:
        import os
        os.environ["JE_AUTOCONTROL_CHATOPS_SCRIPT_ROOT"] = script_root
    return bot


__all__ = ["SlackBot", "SlackError", "make_default_slack_bot"]
