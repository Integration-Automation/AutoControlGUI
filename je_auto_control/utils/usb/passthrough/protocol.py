"""Wire-level frame format for USB passthrough over WebRTC DataChannels.

Frame layout (network byte order)::

    +-----+--------+----------+--------------------+
    | 1B  |   1B   |    2B    |    payload (var)   |
    | op  | flags  | claim_id |                    |
    +-----+--------+----------+--------------------+

The frame is serialised raw (no length prefix) because each WebRTC
DataChannel message is already self-delimiting at the SCTP layer; the
sender writes one frame per ``send()`` call. The 16 KiB payload cap
keeps message sizes well under the recommended SCTP boundary.

Request identity. Every payload that is a JSON object may carry an
optional ``"request_id"`` string (1..64 characters). The viewer generates
it and puts it in each request (OPEN, RESUME, LIST, CLOSE, CTRL, BULK,
INT); the host copies it unchanged into every reply to that request
(OPENED, LIST, CLOSED, CTRL, BULK, INT, ERROR), so the viewer pairs a
reply with the request that asked for it rather than with whichever
request of that kind is waiting. CREDIT frames never carry one: a credit
is a grant on the claim, not an answer. The field is optional in both
directions -- a host that receives no id (or one it cannot echo) replies
exactly as it did before the field existed, and a viewer that receives
no id falls back to pairing by kind.

This module is pure data — no I/O, no asyncio, no peer connection.
"""
from __future__ import annotations

import enum
import json
import struct
from dataclasses import dataclass
from typing import Any, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException


_HEADER_FORMAT = "!BBH"
HEADER_BYTES = struct.calcsize(_HEADER_FORMAT)
MAX_PAYLOAD_BYTES = 16 * 1024
FLAG_EOF = 0x01
#: JSON key of the optional request identity, and the longest id a host echoes.
REQUEST_ID_KEY = "request_id"
MAX_REQUEST_ID_CHARS = 64


class Opcode(enum.IntEnum):
    """One-byte opcodes carried in the frame header."""

    LIST = 0x01
    OPEN = 0x02
    OPENED = 0x03
    CTRL = 0x04
    BULK = 0x05
    INT = 0x06
    CREDIT = 0x07
    CLOSE = 0x08
    CLOSED = 0x09
    RESUME = 0x0A
    ERROR = 0xFF


class ProtocolError(AutoControlException):
    """Raised on malformed frames or invariant violations."""


@dataclass(frozen=True)
class Frame:
    """One decoded protocol frame."""

    op: Opcode
    flags: int = 0
    claim_id: int = 0
    payload: bytes = b""

    def __post_init__(self) -> None:
        if not isinstance(self.op, Opcode):
            raise ProtocolError(f"op must be an Opcode, got {self.op!r}")
        if not 0 <= int(self.flags) <= 0xFF:
            raise ProtocolError(f"flags out of range: {self.flags}")
        if not 0 <= int(self.claim_id) <= 0xFFFF:
            raise ProtocolError(f"claim_id out of range: {self.claim_id}")
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise ProtocolError("payload must be bytes-like")
        if len(self.payload) > MAX_PAYLOAD_BYTES:
            raise ProtocolError(
                f"payload {len(self.payload)} exceeds cap {MAX_PAYLOAD_BYTES}",
            )


def encode_frame(frame: Frame) -> bytes:
    """Serialise a :class:`Frame` to the wire format."""
    header = struct.pack(
        _HEADER_FORMAT,
        int(frame.op), int(frame.flags), int(frame.claim_id),
    )
    return header + bytes(frame.payload)


def fragment_payload(op: "Opcode", claim_id: int, payload: bytes,
                     *, base_flags: int = 0) -> list:
    """Split ``payload`` into EOF-terminated frames (open question 2).

    A payload that fits in a single frame yields exactly one frame with
    :data:`FLAG_EOF` set. A larger payload is chunked at
    :data:`MAX_PAYLOAD_BYTES`; every chunk but the last clears
    ``FLAG_EOF`` and the receiver reassembles by concatenating payloads
    of consecutive same-``claim_id`` frames until the EOF flag arrives.
    """
    data = bytes(payload)
    frames = []
    if not data:
        return [Frame(op=op, flags=base_flags | FLAG_EOF,
                      claim_id=claim_id, payload=b"")]
    for start in range(0, len(data), MAX_PAYLOAD_BYTES):
        chunk = data[start:start + MAX_PAYLOAD_BYTES]
        is_last = start + MAX_PAYLOAD_BYTES >= len(data)
        flags = base_flags | (FLAG_EOF if is_last else 0)
        frames.append(Frame(op=op, flags=flags,
                            claim_id=claim_id, payload=chunk))
    return frames


def decode_frame(data: bytes) -> Frame:
    """Parse one frame from ``data``; raise :class:`ProtocolError` on failure."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ProtocolError("data must be bytes-like")
    if len(data) < HEADER_BYTES:
        raise ProtocolError(
            f"frame too short ({len(data)}B); need at least {HEADER_BYTES}",
        )
    op_raw, flags, claim_id = struct.unpack_from(_HEADER_FORMAT, data, 0)
    try:
        op = Opcode(op_raw)
    except ValueError as error:
        raise ProtocolError(f"unknown opcode 0x{op_raw:02x}") from error
    payload = bytes(data[HEADER_BYTES:])
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ProtocolError(
            f"payload {len(payload)} exceeds cap {MAX_PAYLOAD_BYTES}",
        )
    return Frame(op=op, flags=flags, claim_id=claim_id, payload=payload)


def valid_request_id(value: Any) -> bool:
    """True if ``value`` is a request id a peer may send and echo."""
    return isinstance(value, str) and 0 < len(value) <= MAX_REQUEST_ID_CHARS


def request_id_of(payload: bytes) -> Optional[str]:
    """The ``request_id`` of a JSON payload, or ``None`` if it has none.

    Never raises: an empty payload, one that is not a JSON object, or an
    id that is not a 1..64 character string all mean "no id", which is
    what a peer older than the field sends.
    """
    if not payload:
        return None
    try:
        decoded = json.loads(bytes(payload).decode("utf-8"))
    except ValueError:      # UnicodeDecodeError and JSONDecodeError both are
        return None
    if not isinstance(decoded, dict):
        return None
    value = decoded.get(REQUEST_ID_KEY)
    return value if valid_request_id(value) else None


__all__ = [
    "Frame", "Opcode", "ProtocolError",
    "decode_frame", "encode_frame", "fragment_payload",
    "request_id_of", "valid_request_id",
    "MAX_PAYLOAD_BYTES", "HEADER_BYTES", "FLAG_EOF",
    "REQUEST_ID_KEY", "MAX_REQUEST_ID_CHARS",
]
