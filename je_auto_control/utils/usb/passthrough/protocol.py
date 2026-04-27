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

This module is pure data — no I/O, no asyncio, no peer connection.
"""
from __future__ import annotations

import enum
import struct
from dataclasses import dataclass


_HEADER_FORMAT = "!BBH"
HEADER_BYTES = struct.calcsize(_HEADER_FORMAT)
MAX_PAYLOAD_BYTES = 16 * 1024
FLAG_EOF = 0x01


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
    ERROR = 0xFF


class ProtocolError(Exception):
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


__all__ = [
    "Frame", "Opcode", "ProtocolError",
    "decode_frame", "encode_frame",
    "MAX_PAYLOAD_BYTES", "HEADER_BYTES", "FLAG_EOF",
]
