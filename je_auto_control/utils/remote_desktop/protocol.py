"""Length-prefixed framing for the remote-desktop TCP protocol.

Wire format per message: ``MAGIC(2) | TYPE(1) | LENGTH(4 BE) | PAYLOAD``.
Payload size is capped to keep a misbehaving peer from forcing the host
to allocate gigabyte buffers. Helpers here only deal with bytes — auth
and high-level semantics live in :mod:`auth`, :mod:`host`, :mod:`viewer`.
"""
import enum
import struct
from typing import Tuple

_MAGIC = b"AC"
_HEADER_FMT = "!2sBI"
HEADER_SIZE = struct.calcsize(_HEADER_FMT)
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024  # 16 MiB hard cap


class ProtocolError(RuntimeError):
    """Raised when an incoming frame violates the wire format."""


class AuthenticationError(RuntimeError):
    """Raised when the HMAC handshake fails."""


class MessageType(enum.IntEnum):
    """Single-byte type tags for every protocol message."""

    AUTH_CHALLENGE = 0x01  # host -> viewer: random nonce
    AUTH_RESPONSE = 0x02  # viewer -> host: HMAC of nonce
    AUTH_OK = 0x03  # host -> viewer: handshake accepted
    AUTH_FAIL = 0x04  # host -> viewer: handshake rejected
    FRAME = 0x10  # host -> viewer: JPEG frame
    INPUT = 0x20  # viewer -> host: JSON input message
    PING = 0x30  # either way: liveness


def encode_frame(message_type: MessageType, payload: bytes = b"") -> bytes:
    """Serialise ``payload`` with a typed header."""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ProtocolError(
            f"payload too large: {len(payload)} > {MAX_PAYLOAD_BYTES}"
        )
    header = struct.pack(_HEADER_FMT, _MAGIC, int(message_type), len(payload))
    return header + bytes(payload)


def decode_frame_header(header: bytes) -> Tuple[MessageType, int]:
    """Validate the header bytes and return ``(type, length)``."""
    if len(header) != HEADER_SIZE:
        raise ProtocolError(
            f"header must be {HEADER_SIZE} bytes, got {len(header)}"
        )
    magic, type_byte, length = struct.unpack(_HEADER_FMT, header)
    if magic != _MAGIC:
        raise ProtocolError(f"bad magic: {magic!r}")
    if length > MAX_PAYLOAD_BYTES:
        raise ProtocolError(
            f"declared payload too large: {length} > {MAX_PAYLOAD_BYTES}"
        )
    try:
        return MessageType(type_byte), int(length)
    except ValueError as error:
        raise ProtocolError(f"unknown message type 0x{type_byte:02x}") from error


def read_exact(sock, length: int) -> bytes:
    """Read exactly ``length`` bytes from ``sock`` or raise ConnectionError."""
    chunks = []
    remaining = length
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("peer closed connection")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_message(sock) -> Tuple[MessageType, bytes]:
    """Read one full ``(type, payload)`` message from ``sock``."""
    header = read_exact(sock, HEADER_SIZE)
    msg_type, length = decode_frame_header(header)
    payload = read_exact(sock, length) if length else b""
    return msg_type, payload
