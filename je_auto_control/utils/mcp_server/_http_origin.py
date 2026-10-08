"""Which browser origins and ``Host`` names the MCP HTTP transport answers.

Split out of :mod:`.http_transport`. With no token configured (the default)
any web page the user opened could POST ``tools/call`` to the server as a
simple ``text/plain`` request, which browsers send without a CORS preflight;
the MCP specification requires servers to validate ``Origin`` for exactly
this.
"""
import os
from typing import Any
from urllib.parse import urlsplit

#: Host names that mean this machine. ``urlsplit`` strips IPv6 brackets.
LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})

#: Extra browser origins allowed to call the server, comma-separated and
#: exact (``https://example.test:8443``); loopback origins always are.
ALLOWED_ORIGINS_ENV = "JE_AUTOCONTROL_MCP_ALLOWED_ORIGINS"


def allowed_origins() -> frozenset:
    """The extra origins ``JE_AUTOCONTROL_MCP_ALLOWED_ORIGINS`` names."""
    raw = os.environ.get(ALLOWED_ORIGINS_ENV, "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def origin_allowed(headers: Any, server_address: Any) -> bool:
    """True unless a browser on another site, or a rebound name, sent this.

    A request without ``Origin`` comes from a non-browser client and is fine.
    When bound to loopback, ``Host`` must also name loopback: a DNS-rebinding
    page reaches 127.0.0.1 under its own name, and a same-origin GET carries
    no ``Origin`` at all.
    """
    origin = headers.get("Origin")
    if origin and origin not in allowed_origins():
        if urlsplit(origin).hostname not in LOOPBACK_NAMES:
            return False
    bound_host = server_address[0] if isinstance(server_address, tuple) else server_address
    if bound_host in LOOPBACK_NAMES:
        host = urlsplit("//" + headers.get("Host", "")).hostname
        if host not in LOOPBACK_NAMES:
            return False
    return True


__all__ = ["ALLOWED_ORIGINS_ENV", "LOOPBACK_NAMES", "allowed_origins", "origin_allowed"]
