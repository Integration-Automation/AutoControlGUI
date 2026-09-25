"""Stdlib-only client for the WebRTC signaling rendezvous service.

Both host and viewer use this to push/poll SDP via a shared signaling URL,
removing the manual copy/paste of Phase 1. Network errors raise
:class:`SignalingError`; 404s on poll endpoints return ``None`` so callers
can re-poll cleanly.

No third-party HTTP dep — everything goes through the package's
``http_client``, so the scheme allow-list and the egress policy apply.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from typing import Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_TIMEOUT_S = 5.0
_POLL_INTERVAL_S = 1.0


class SignalingError(AutoControlException, RuntimeError):
    """Network or protocol error talking to the signaling server."""


def _request(method: str, url: str, *,
             body: Optional[dict] = None,
             secret: Optional[str] = None,
             timeout: float = _DEFAULT_TIMEOUT_S) -> Optional[dict]:
    from je_auto_control.utils.http_client.http_client import build_call, perform_call
    headers = {"X-Signaling-Secret": secret} if secret else None
    try:
        call = build_call(url, method, headers=headers, json_body=body, timeout=timeout)
        # Without following redirects, as config sync does: urlopen carried
        # X-Signaling-Secret to whatever host a redirect named. It also read
        # file:// URLs, and raised ValueError for a URL with no scheme.
        call["follow_redirects"] = False
        response = perform_call(call)
    except (OSError, ValueError) as error:
        # A timeout, a hang-up, a refused scheme or egress host: the GUI
        # workers catch only SignalingError, so these ended their threads.
        raise SignalingError(f"signaling {method} {url} failed: {error!r}") from error
    return _json_reply(method, url, response)


def _json_reply(method: str, url: str, response: dict) -> Optional[dict]:
    """The reply's JSON object: ``None`` for a 404, ``{}`` for an empty body."""
    status = int(response["status"])
    if status == 404:
        return None
    if not 200 <= status < 300:
        raise SignalingError(f"signaling {method} {url} -> HTTP {status}")
    if not response.get("text"):
        return {}
    try:
        payload = json.loads(response["text"])
    except (ValueError, RecursionError) as error:
        raise SignalingError("signaling: bad JSON response") from error
    if not isinstance(payload, dict):
        # The fetchers read .get("sdp") from it: a list raised AttributeError.
        raise SignalingError("signaling: the reply is not a JSON object")
    return payload


def _sdp(response: Optional[dict]) -> Optional[str]:
    """The ``sdp`` field of a fetch reply, which must be a string when present."""
    if response is None:
        return None
    sdp = response.get("sdp")
    if sdp is not None and not isinstance(sdp, str):
        raise SignalingError("signaling: 'sdp' is not a string")
    return sdp


def _build_url(server_url: str, host_id: str, suffix: str) -> str:
    base = server_url.rstrip("/")
    encoded_id = urllib.parse.quote(host_id, safe="")
    return f"{base}/sessions/{encoded_id}/{suffix}"


def push_offer(server_url: str, host_id: str, offer_sdp: str, *,
               secret: Optional[str] = None,
               timeout: float = _DEFAULT_TIMEOUT_S) -> None:
    """Host → server: register an offer for this host_id."""
    _request("POST", _build_url(server_url, host_id, "offer"),
             body={"sdp": offer_sdp}, secret=secret, timeout=timeout)


def fetch_offer(server_url: str, host_id: str, *,
                secret: Optional[str] = None,
                timeout: float = _DEFAULT_TIMEOUT_S) -> Optional[str]:
    """Viewer → server: pull the host's pending offer (None if not posted)."""
    return _sdp(_request("GET", _build_url(server_url, host_id, "offer"),
                         secret=secret, timeout=timeout))


def push_answer(server_url: str, host_id: str, answer_sdp: str, *,
                secret: Optional[str] = None,
                timeout: float = _DEFAULT_TIMEOUT_S) -> bool:
    """Viewer → server: post an answer. Returns False if no offer existed."""
    response = _request("POST", _build_url(server_url, host_id, "answer"),
                        body={"sdp": answer_sdp}, secret=secret,
                        timeout=timeout)
    return response is not None


def fetch_answer(server_url: str, host_id: str, *,
                 secret: Optional[str] = None,
                 timeout: float = _DEFAULT_TIMEOUT_S) -> Optional[str]:
    """Host → server: poll for the viewer's answer."""
    return _sdp(_request("GET", _build_url(server_url, host_id, "answer"),
                         secret=secret, timeout=timeout))


def wait_for_answer(server_url: str, host_id: str, *,
                    secret: Optional[str] = None,
                    timeout_s: float = 60.0,
                    poll_interval_s: float = _POLL_INTERVAL_S) -> str:
    """Host: block until viewer posts an answer or ``timeout_s`` elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        answer = fetch_answer(server_url, host_id, secret=secret)
        if answer is not None:
            return answer
        time.sleep(poll_interval_s)
    raise SignalingError(f"no answer for host_id={host_id} within {timeout_s}s")


def wait_for_offer(server_url: str, host_id: str, *,
                   secret: Optional[str] = None,
                   timeout_s: float = 60.0,
                   poll_interval_s: float = _POLL_INTERVAL_S) -> str:
    """Viewer: block until host posts an offer or ``timeout_s`` elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        offer = fetch_offer(server_url, host_id, secret=secret)
        if offer is not None:
            return offer
        time.sleep(poll_interval_s)
    raise SignalingError(f"no offer for host_id={host_id} within {timeout_s}s")


def delete_session(server_url: str, host_id: str, *,
                   secret: Optional[str] = None,
                   timeout: float = _DEFAULT_TIMEOUT_S) -> None:
    """Best-effort cleanup; ignores missing sessions."""
    base = server_url.rstrip("/")
    encoded_id = urllib.parse.quote(host_id, safe="")
    url = f"{base}/sessions/{encoded_id}"
    try:
        _request("DELETE", url, secret=secret, timeout=timeout)
    except SignalingError as error:
        autocontrol_logger.debug("signaling delete failed: %r", error)


__all__ = [
    "SignalingError",
    "push_offer", "fetch_offer", "push_answer", "fetch_answer",
    "wait_for_offer", "wait_for_answer", "delete_session",
]
