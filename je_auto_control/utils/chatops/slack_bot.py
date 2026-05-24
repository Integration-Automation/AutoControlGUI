"""Slack adapter for :class:`CommandRouter`.

Polling-only by default — no need for a public webhook URL or signing
secret. Reads the last N messages from one channel via
``conversations.history``, hands every new message to the router, and
posts replies with ``chat.postMessage``. Suitable for internal
infrastructure where the bot lives on a private network and pulls
work rather than receiving pushes.

Three pieces of state are tracked per channel:

* ``last_seen_ts`` — the Slack timestamp of the most-recent message we
  have already routed; persisted across ``poll_once`` calls;
* ``bot_user_id`` — the bot's own user id, looked up lazily so we
  don't loop on our own replies;
* ``error_backoff_s`` — multiplicative back-off on consecutive
  failures, capped so the poller stays responsive.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from je_auto_control.utils.chatops.router import CommandResult, CommandRouter
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_SLACK_API = "https://slack.com/api"
_HTTP_TIMEOUT = 15.0
_MIN_POLL_INTERVAL = 1.0
_MAX_BACKOFF = 60.0


class SlackError(RuntimeError):
    """Raised when the Slack API returns ``ok: false`` or HTTP fails."""


@dataclass
class SlackBot:
    """Polling Slack adapter wrapped around a :class:`CommandRouter`."""

    token: str
    channel_id: str
    router: CommandRouter
    poll_interval_s: float = 5.0
    last_seen_ts: Optional[str] = None
    _bot_user_id: Optional[str] = None
    _stop: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        if not self.token or not self.token.startswith("xox"):
            raise SlackError("Slack token must start with 'xox' (bot token)")
        if not self.channel_id:
            raise SlackError("channel_id must be a non-empty string")
        if self.poll_interval_s < _MIN_POLL_INTERVAL:
            raise SlackError(
                f"poll_interval_s must be >= {_MIN_POLL_INTERVAL}",
            )

    # --- polling -------------------------------------------------

    def poll_once(self) -> int:
        """Pull new messages, dispatch each through the router. Returns count."""
        messages = self._fetch_messages()
        if not messages:
            return 0
        # Slack returns newest-first; reverse so we route in chronological order.
        ordered = list(reversed(messages))
        dispatched = 0
        latest_ts = self.last_seen_ts or "0"
        for msg in ordered:
            ts = str(msg.get("ts") or "")
            if not ts:
                continue
            latest_ts = max(latest_ts, ts)
            if self._is_self(msg):
                continue
            text = str(msg.get("text") or "")
            if self._route_one(text, msg) is not None:
                dispatched += 1
        self.last_seen_ts = latest_ts
        return dispatched

    def run_forever(self, *, max_iterations: Optional[int] = None) -> None:
        """Poll on a loop until :meth:`stop` is called."""
        self._stop.clear()
        backoff = 0.0
        iteration = 0
        while not self._stop.is_set():
            try:
                self.poll_once()
                backoff = 0.0
            except SlackError as error:
                autocontrol_logger.warning(f"chatops slack poll: {error}")
                backoff = min(_MAX_BACKOFF, max(backoff * 2, 2.0))
            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                return
            self._stop.wait(self.poll_interval_s + backoff)

    def stop(self) -> None:
        self._stop.set()

    # --- routing -------------------------------------------------

    def _route_one(self, text: str,
                   message: Dict[str, Any]) -> Optional[CommandResult]:
        try:
            result = self.router.dispatch(
                text, context={"slack_user": message.get("user"),
                                "slack_ts": message.get("ts"),
                                "slack_channel": self.channel_id},
            )
        except (RuntimeError, ValueError) as error:
            self.post_message(f"router error: {error}")
            return None
        if result is None:
            return None
        self.post_message(result.text, thread_ts=str(message.get("ts") or ""))
        return result

    # --- HTTP wrappers -------------------------------------------

    def post_message(self, text: str,
                     *, thread_ts: str = "") -> Dict[str, Any]:
        payload: Dict[str, Any] = {"channel": self.channel_id, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return self._api_post("chat.postMessage", payload)

    def _fetch_messages(self) -> list:
        params: Dict[str, Any] = {
            "channel": self.channel_id,
            "limit": 50,
        }
        if self.last_seen_ts:
            params["oldest"] = self.last_seen_ts
        body = self._api_get("conversations.history", params)
        return list(body.get("messages") or [])

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
        headers = {"Authorization": f"Bearer {self.token}"}
        data: Optional[bytes] = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(  # nosec B310  # reason: scheme allow-listed above
            url, data=data, method=method, headers=headers,
        )
        try:
            with urllib.request.urlopen(  # nosec B310
                    request, timeout=_HTTP_TIMEOUT,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as error:
            raise SlackError(f"HTTP failure: {error}") from error
        except ValueError as error:
            raise SlackError(f"non-JSON response: {error}") from error
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
