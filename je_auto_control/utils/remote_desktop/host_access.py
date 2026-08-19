"""Viewer approval and access control for the TCP remote-desktop host.

The gate a viewer passes through after the HMAC handshake and before any
frame is sent: the snapshot handed to the approval callback, how that
callback's return value maps to a permission, the TOTP codes accepted for
a share code, and the IP allowlist. Shared by :mod:`host` and
:mod:`host_client`, which is why it is its own module rather than living
in either.
"""
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


@dataclass(frozen=True)
class PendingViewer:
    """Snapshot of an authenticated viewer awaiting host approval.

    Passed to the ``on_pending_viewer`` callback after the HMAC handshake
    succeeds but before the host starts streaming frames. The callback's
    return value is interpreted as:

    * ``True``  / ``"full"``      → admit with full control
    * ``"view_only"``             → admit, but drop incoming INPUT messages
    * ``False`` / ``None`` / etc. → reject
    """
    address: tuple
    host_id: str
    transport: str = "tcp"

PendingViewerCallback = Callable[[PendingViewer], Any]
"""Callback signature: see :class:`PendingViewer` for return value semantics."""

PERMISSION_FULL = "full"
PERMISSION_VIEW_ONLY = "view_only"
PERMISSION_DENIED = "denied"

def _interpret_approval(result: Any) -> str:
    """Map an approval-callback return value to a permission string.

    Backward compatibility: any truthy value other than the literal
    ``"view_only"`` / ``"denied"`` strings is treated as full-control
    admit. Falsy values are denied.
    """
    if result == PERMISSION_VIEW_ONLY:
        return PERMISSION_VIEW_ONLY
    if result == PERMISSION_DENIED or not result:
        return PERMISSION_DENIED
    return PERMISSION_FULL

_AUTH_TIMEOUT_S = 60.0

def _candidate_totp_codes(secret: str):
    """Yield TOTP codes within ±1 step of the current 30-second window."""
    from je_auto_control.utils.remote_desktop.totp import generate_code
    now = time.time()
    for delta in (-1, 0, 1):
        yield generate_code(secret, at=now + (delta * 30.0))

def _compile_ip_allowlist(
        entries: Optional[Sequence[str]]) -> Optional[List[Any]]:
    """Pre-parse ``entries`` into ``ip_address`` / ``ip_network`` objects.

    ``None`` or an empty list → no filtering (allow all). Entries are
    plain IPs (``"192.168.1.10"``) or CIDR ranges (``"10.0.0.0/8"``);
    unparseable entries are dropped with a warning so a typo doesn't
    silently broaden access.
    """
    if not entries:
        return None
    import ipaddress
    compiled: List[Any] = []
    for entry in entries:
        text = str(entry).strip()
        if not text:
            continue
        try:
            if "/" in text:
                compiled.append(ipaddress.ip_network(text, strict=False))
            else:
                compiled.append(ipaddress.ip_address(text))
        except ValueError:
            autocontrol_logger.warning(
                "remote_desktop ip_allowlist entry rejected: %r", text,
            )
    return compiled or None

def _ip_in_allowlist(allowlist: Optional[List[Any]], peer_ip: str) -> bool:
    """Return True when ``peer_ip`` matches any allowlist entry (or no list)."""
    if not allowlist:
        return True
    import ipaddress
    try:
        addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    for entry in allowlist:
        if isinstance(entry, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            if addr in entry:
                return True
        elif entry == addr:
            return True
    return False
