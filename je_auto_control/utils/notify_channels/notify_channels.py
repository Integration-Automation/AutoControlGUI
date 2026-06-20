"""Send notifications to chat/webhook endpoints (Slack/Discord/Teams/raw).

The built-in ``notify`` is desktop-toast only and ChatOps shipped Slack as the
only transport; unattended runs want to alert Teams/Discord/generic webhooks
too. Each is a simple JSON POST with a transport-specific payload shape — Slack
and a Teams MessageCard use ``text``, Discord uses ``content`` — so this builds
the right body and POSTs it through the egress-guarded HTTP client.

The transport is injectable (a ``poster`` callable or a module-level default),
so sending is unit-testable with no network. Pure standard library; imports no
``PySide6``.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

TRANSPORT_RAW = "raw"
TRANSPORT_SLACK = "slack"
TRANSPORT_DISCORD = "discord"
TRANSPORT_TEAMS = "teams"

_STATE: Dict[str, Any] = {"poster": None}


@dataclass(frozen=True)
class WebhookResult:
    """The outcome of a webhook notification."""

    ok: bool
    status: int
    transport: str


def set_default_poster(poster: Optional[Callable[[str, Dict[str, Any]], int]]
                       ) -> None:
    """Install a module-level transport ``poster(url, payload) -> status``."""
    _STATE["poster"] = poster


def _payload(transport: str, text: str, title: Optional[str]) -> Dict[str, Any]:
    if transport == TRANSPORT_DISCORD:
        body = f"**{title}**\n{text}" if title else text
        return {"content": body}
    if transport == TRANSPORT_TEAMS:
        card: Dict[str, Any] = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "text": text,
        }
        if title:
            card["title"] = title
        return card
    if transport == TRANSPORT_SLACK:
        return {"text": f"*{title}*\n{text}" if title else text}
    payload: Dict[str, Any] = {"text": text}
    if title:
        payload["title"] = title
    return payload


def _default_poster(url: str, payload: Dict[str, Any]) -> int:
    from je_auto_control.utils.http_client.http_client import http_request
    response = http_request(url, method="POST", json_body=payload, timeout=10.0)
    return int(response.get("status", 0))


class WebhookChannel:
    """A notification channel for one webhook URL and transport."""

    def __init__(self, url: str, *, transport: str = TRANSPORT_RAW,
                 poster: Optional[Callable[[str, Dict[str, Any]], int]] = None
                 ) -> None:
        """``transport`` shapes the payload; ``poster`` overrides the sender."""
        self._url = url
        self._transport = transport
        self._poster = poster

    def send(self, text: str, *, title: Optional[str] = None) -> WebhookResult:
        """Post ``text`` (and optional ``title``) to the channel."""
        poster = self._poster or _STATE["poster"] or _default_poster
        status = int(poster(self._url, _payload(self._transport, text, title)))
        return WebhookResult(200 <= status < 300, status, self._transport)


def notify_webhook(url: str, text: str, *, transport: str = TRANSPORT_RAW,
                   title: Optional[str] = None,
                   poster: Optional[Callable[[str, Dict[str, Any]], int]] = None
                   ) -> WebhookResult:
    """Send a one-off webhook notification; return a :class:`WebhookResult`."""
    return WebhookChannel(url, transport=transport, poster=poster).send(
        text, title=title)
