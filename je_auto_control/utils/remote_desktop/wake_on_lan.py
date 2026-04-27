"""Send a Wake-on-LAN magic packet to a sleeping host on the LAN.

The magic packet is six 0xFF bytes followed by the target's MAC repeated
16 times. Sent as UDP broadcast to port 9 by default. Only works on the
same broadcast domain unless your router forwards directed broadcasts —
WAN wake usually needs a port-forward + a "subnet-directed broadcast"
exception, which most consumer routers do not allow.
"""
from __future__ import annotations

import re
import socket
from typing import Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_MAC_PATTERN = re.compile(r"^[0-9a-fA-F]{2}([:\-]?[0-9a-fA-F]{2}){5}$")
_DEFAULT_PORT = 9
_DEFAULT_BROADCAST = "255.255.255.255"


def _normalize_mac(mac: str) -> bytes:
    if not isinstance(mac, str) or _MAC_PATTERN.fullmatch(mac.strip()) is None:
        raise ValueError(f"invalid MAC address: {mac!r}")
    cleaned = re.sub(r"[:\-]", "", mac.strip())
    return bytes.fromhex(cleaned)


def build_magic_packet(mac: str) -> bytes:
    """Return the 102-byte magic packet for ``mac`` (e.g. ``"AA:BB:..."``)."""
    mac_bytes = _normalize_mac(mac)
    return b"\xff" * 6 + mac_bytes * 16


def send_magic_packet(mac: str, *,
                      broadcast_address: Optional[str] = None,
                      port: int = _DEFAULT_PORT) -> None:
    """Broadcast a Wake-on-LAN magic packet for ``mac``."""
    payload = build_magic_packet(mac)
    address = broadcast_address or _DEFAULT_BROADCAST
    if not 1 <= port <= 65535:
        raise ValueError(f"port must be 1..65535, got {port}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(payload, (address, port))
        autocontrol_logger.info(
            "wake_on_lan: sent magic packet for %s -> %s:%d",
            mac, address, port,
        )
    finally:
        sock.close()


__all__ = ["build_magic_packet", "send_magic_packet"]
