"""Decide which Remote Desktop transport to use from a user-typed target.

The coordinator is the headless brain behind the AnyDesk-style Quick
Connect input box: paste a string, get back a structured ``ConnectTarget``
describing which transport to drive. It performs no I/O — it is pure
parsing.

Recognised input forms::

    192.168.1.10:5555      -> ConnectTarget(kind="tcp", host=..., port=...)
    tcp://192.168.1.10:55  -> ConnectTarget(kind="tcp", host=..., port=...)
    ws://host:8765         -> ConnectTarget(kind="ws", host=..., port=..., path="/")
    ws://host:8765/foo     -> ConnectTarget(kind="ws", host=..., port=..., path="/foo")
    wss://host:8765/foo    -> ConnectTarget(kind="wss", host=..., port=..., path="/foo")
    123456789              -> ConnectTarget(kind="webrtc_id", host_id="123456789")
    123-456-789            -> ConnectTarget(kind="webrtc_id", host_id="123456789")
    123 456 789            -> ConnectTarget(kind="webrtc_id", host_id="123456789")

Anything else raises :class:`UnresolvableTargetError` so the caller can
ask the user to re-enter rather than silently picking the wrong transport.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from je_auto_control.utils.remote_desktop.host_id import (
    HostIdError, parse_host_id,
)

_TCP_SCHEMES = ("tcp://",)
_WS_SCHEME = "ws://"
_WSS_SCHEME = "wss://"
_DIGIT_GROUP_PATTERN = re.compile(r"^[\d\s\-_]+$")
_MIN_PORT = 1
_MAX_PORT = 65535


class UnresolvableTargetError(ValueError):
    """The input does not match any recognised transport form."""


@dataclass(frozen=True)
class ConnectTarget:
    """Structured description of a Remote Desktop connection target.

    ``kind`` is one of ``"tcp"``, ``"ws"``, ``"wss"``, or ``"webrtc_id"``.
    Direct-transport fields (``host``, ``port``, ``path``) are populated
    for the TCP / WS / WSS kinds; ``host_id`` is populated for
    ``"webrtc_id"``. The caller is expected to dispatch on ``kind`` and
    use the relevant fields.
    """
    kind: str
    host: Optional[str] = None
    port: Optional[int] = None
    path: Optional[str] = None
    host_id: Optional[str] = None

    @property
    def is_direct(self) -> bool:
        """True for transports that connect to a literal ``host:port``."""
        return self.kind in ("tcp", "ws", "wss")


def _parse_host_port(rest: str) -> tuple:
    """Split ``host:port[/path]`` and validate each piece."""
    if "/" in rest:
        authority, _slash, path = rest.partition("/")
        path = "/" + path
    else:
        authority, path = rest, "/"
    if ":" not in authority:
        raise UnresolvableTargetError(
            f"expected host:port, got {authority!r}"
        )
    host, _sep, port_text = authority.rpartition(":")
    host = host.strip()
    try:
        port = int(port_text.strip())
    except ValueError as exc:
        raise UnresolvableTargetError(
            f"port must be an integer, got {port_text!r}"
        ) from exc
    if not host or port < _MIN_PORT or port > _MAX_PORT:
        raise UnresolvableTargetError(
            f"host must be non-empty and port in {_MIN_PORT}-{_MAX_PORT}"
        )
    return host, port, path


def _try_parse_webrtc_id(text: str) -> Optional[ConnectTarget]:
    """Return a webrtc_id target if ``text`` looks like a 9-digit host ID."""
    if not _DIGIT_GROUP_PATTERN.fullmatch(text):
        return None
    try:
        host_id = parse_host_id(text)
    except HostIdError:
        return None
    return ConnectTarget(kind="webrtc_id", host_id=host_id)


def _parse_scheme(text: str) -> Optional[ConnectTarget]:
    """Return a transport target if ``text`` begins with a known scheme."""
    if text.startswith(_TCP_SCHEMES):
        host, port, _path = _parse_host_port(text[len("tcp://"):])
        return ConnectTarget(kind="tcp", host=host, port=port)
    if text.startswith(_WSS_SCHEME):
        host, port, path = _parse_host_port(text[len(_WSS_SCHEME):])
        return ConnectTarget(kind="wss", host=host, port=port, path=path)
    if text.startswith(_WS_SCHEME):
        host, port, path = _parse_host_port(text[len(_WS_SCHEME):])
        return ConnectTarget(kind="ws", host=host, port=port, path=path)
    return None


def parse_target(text: str) -> ConnectTarget:
    """Turn user-typed text into a structured :class:`ConnectTarget`.

    Raises :class:`UnresolvableTargetError` when the input matches no
    recognised form, so callers can surface a clear error message
    rather than silently picking the wrong transport.
    """
    if not isinstance(text, str):
        raise UnresolvableTargetError(
            f"target must be a string, got {type(text).__name__}"
        )
    cleaned = text.strip()
    if not cleaned:
        raise UnresolvableTargetError("target is empty")

    scheme_target = _parse_scheme(cleaned)
    if scheme_target is not None:
        return scheme_target

    webrtc_target = _try_parse_webrtc_id(cleaned)
    if webrtc_target is not None:
        return webrtc_target

    # No scheme, not a 9-digit ID → must be bare host:port for TCP.
    host, port, _path = _parse_host_port(cleaned)
    return ConnectTarget(kind="tcp", host=host, port=port)


__all__ = [
    "ConnectTarget", "UnresolvableTargetError", "parse_target",
]
