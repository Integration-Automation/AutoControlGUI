"""Minimal RFC 6455 WebSocket framing + handshake helpers.

This is the smallest implementation that round-trips our typed-message
payloads as WebSocket BINARY frames. It deliberately rejects fragmented
data frames (FIN must be 1) — every typed message we send fits in a
single ~16 MiB WS frame, so reassembly machinery would only add risk
without buying anything. PING / PONG control frames are handled
transparently in :func:`recv_message`.
"""
import base64
import contextlib
import hashlib
import os
import socket
import struct
import threading
from typing import Optional, Tuple

from je_auto_control.utils.remote_desktop.protocol import ProtocolError

WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OPCODE_CONTINUATION = 0x0
OPCODE_TEXT = 0x1
OPCODE_BINARY = 0x2
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA

MAX_FRAME_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_HEADER_BYTES = 8192


class WsProtocolError(ProtocolError):
    """Raised when a peer breaks the WebSocket framing contract."""
    # A ProtocolError, so every receive loop that ends a connection on a
    # malformed frame ends it on a malformed WebSocket frame too; as a bare
    # RuntimeError one TEXT frame killed the host's and the viewer's
    # receive threads while the session stayed registered.



class WsClosedError(ConnectionError):
    """Raised when the peer sends a CLOSE frame."""


# --- handshake ------------------------------------------------------------


def server_handshake(sock: socket.socket) -> str:
    """Read the HTTP upgrade request and reply ``101 Switching Protocols``.

    Returns the request path (``"/"`` for unspecified), so callers can
    route on it later if they want to host multiple services on one port.
    """
    request = _read_http_message(sock)
    request_line = request.split("\r\n", 1)[0]
    parts = request_line.split(" ")
    if len(parts) < 3 or parts[0].upper() != "GET":
        _send_http_error(sock, 400, "Bad Request")
        raise WsProtocolError(f"bad request line {request_line!r}")
    path = parts[1] or "/"
    headers = _parse_headers(request)
    if "websocket" not in headers.get("upgrade", "").lower():
        _send_http_error(sock, 400, "Bad Request: Upgrade")
        raise WsProtocolError("missing websocket upgrade header")
    if "upgrade" not in headers.get("connection", "").lower():
        _send_http_error(sock, 400, "Bad Request: Connection")
        raise WsProtocolError("missing connection upgrade header")
    key = headers.get("sec-websocket-key")
    if not key or not _is_valid_key(key):
        _send_http_error(sock, 400, "Bad Request: Sec-WebSocket-Key")
        raise WsProtocolError("missing or malformed Sec-WebSocket-Key")
    accept = _compute_accept(key)
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    ).encode("ascii")
    sock.sendall(response)
    return path


def client_handshake(sock: socket.socket, host: str, port: int,
                     path: str = "/") -> None:
    """Send the HTTP upgrade and validate the ``101`` reply."""
    key_bytes = os.urandom(16)
    key = base64.b64encode(key_bytes).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode("ascii")
    sock.sendall(request)
    response = _read_http_message(sock)
    status = _parse_status(response)
    if status != 101:
        raise WsProtocolError(f"server returned status {status}")
    headers = _parse_headers(response)
    if "websocket" not in headers.get("upgrade", "").lower():
        raise WsProtocolError("server missing Upgrade: websocket")
    expected = _compute_accept(key)
    if headers.get("sec-websocket-accept", "") != expected:
        raise WsProtocolError("Sec-WebSocket-Accept mismatch")


def _read_http_message(sock: socket.socket) -> str:
    # Byte-by-byte read until "\r\n\r\n". A bulk recv(1024) would
    # over-read into the next message: when the peer packs the HTTP
    # response and the first protocol frame into a single TCP segment
    # (common on loopback under load), the post-header bytes end up in
    # this buffer and are dropped on return — the next recv() then
    # blocks forever on bytes that already arrived. Loopback syscalls
    # are microseconds; ~150 of them per handshake is well below the
    # noise floor of the WS upgrade itself.
    buf = bytearray()
    terminator = b"\r\n\r\n"
    while not buf.endswith(terminator):
        chunk = sock.recv(1)
        if not chunk:
            raise WsProtocolError("connection closed during handshake")
        buf.extend(chunk)
        if len(buf) > MAX_HEADER_BYTES:
            raise WsProtocolError("HTTP header too large")
    return bytes(buf).decode("iso-8859-1")


def _parse_status(response: str) -> int:
    line = response.split("\r\n", 1)[0]
    parts = line.split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise WsProtocolError(f"bad status line {line!r}")
    return int(parts[1])


def _parse_headers(text: str) -> dict:
    headers = {}
    for line in text.split("\r\n"):
        if ":" in line:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
    return headers


def _is_valid_key(key: str) -> bool:
    """RFC 6455 4.2.1: base64 of exactly 16 bytes.

    A non-ASCII key raised ``UnicodeEncodeError`` past every handler and
    killed the handshake thread with the socket left open.
    """
    try:
        return len(base64.b64decode(key.encode("ascii"), validate=True)) == 16
    except (UnicodeEncodeError, ValueError):   # binascii.Error is a ValueError
        return False


def _compute_accept(key: str) -> str:
    # RFC 6455 mandates SHA-1 for the Sec-WebSocket-Accept handshake;
    # ``usedforsecurity=False`` tells linters this is a protocol-required
    # checksum, not a cryptographic primitive.
    digest = hashlib.sha1(  # nosec B324  # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
        key.encode("ascii") + WS_GUID,
        usedforsecurity=False,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _send_http_error(sock: socket.socket, status: int, message: str) -> None:
    response = (
        f"HTTP/1.1 {status} {message}\r\n"
        "Connection: close\r\n"
        "Content-Length: 0\r\n"
        "\r\n"
    ).encode("ascii")
    try:
        sock.sendall(response)
    except OSError:
        pass


# --- frame I/O ------------------------------------------------------------


def send_binary(sock: socket.socket, payload: bytes,
                mask: bool = False) -> None:
    """Send a single BINARY frame with FIN=1."""
    _send_frame(sock, OPCODE_BINARY, payload, mask=mask)


def send_close(sock: socket.socket, code: int = 1000,
               mask: bool = False) -> None:
    """Send a CLOSE frame with the given status code."""
    _send_frame(sock, OPCODE_CLOSE, struct.pack("!H", code), mask=mask)


def _send_frame(sock: socket.socket, opcode: int, payload: bytes,
                mask: bool) -> None:
    if len(payload) > MAX_FRAME_PAYLOAD_BYTES:
        raise WsProtocolError(
            f"payload too large: {len(payload)} > {MAX_FRAME_PAYLOAD_BYTES}"
        )
    header = bytearray()
    # First byte: FIN bit set, no reserved bits, low nibble is opcode.
    header.append(0x80 | (opcode & 0x0F))
    length = len(payload)
    mask_bit = 0x80 if mask else 0
    if length < 126:
        header.append(mask_bit | length)
    elif length < 0x10000:
        header.append(mask_bit | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(mask_bit | 127)
        header.extend(struct.pack("!Q", length))
    if mask:
        masking_key = os.urandom(4)
        header.extend(masking_key)
        masked = bytes(
            payload[i] ^ masking_key[i % 4] for i in range(length)
        )
        sock.sendall(bytes(header) + masked)
    else:
        sock.sendall(bytes(header) + bytes(payload))


def recv_message(sock: socket.socket, *, mask: bool = False,
                 expect_masked: Optional[bool] = None,
                 send_lock: Optional[threading.Lock] = None) -> bytes:
    """Read one application message (BINARY) and return its payload bytes.

    Control frames (PING / PONG / CLOSE) are handled inline: PINGs get a
    PONG reply, PONGs are dropped, CLOSE raises :class:`WsClosedError`.
    ``mask`` masks that PONG (a client must mask every frame it sends);
    ``expect_masked`` rejects frames whose mask bit differs (a server must
    refuse unmasked client frames, RFC 6455 5.1); ``send_lock`` serialises
    the PONG with the caller's other writes so frames never interleave.
    """
    while True:
        opcode, payload = _read_frame(sock, expect_masked)
        if opcode == OPCODE_BINARY:
            return payload
        if opcode == OPCODE_TEXT:
            raise WsProtocolError("text frames are not supported")
        if opcode == OPCODE_CLOSE:
            raise WsClosedError("peer sent CLOSE")
        if opcode == OPCODE_PING:
            with send_lock or contextlib.nullcontext():
                _send_frame(sock, OPCODE_PONG, payload, mask=mask)
            continue
        if opcode == OPCODE_PONG:
            continue
        if opcode == OPCODE_CONTINUATION:
            raise WsProtocolError("standalone CONTINUATION frame")
        raise WsProtocolError(f"unknown opcode 0x{opcode:x}")


def _read_frame(sock: socket.socket,
                expect_masked: Optional[bool] = None) -> Tuple[int, bytes]:
    header = _read_exact(sock, 2)
    fin = (header[0] & 0x80) != 0
    rsv = (header[0] >> 4) & 0x07
    opcode = header[0] & 0x0F
    masked = (header[1] & 0x80) != 0
    if rsv != 0:
        raise WsProtocolError("RSV bits set")
    if not fin:
        raise WsProtocolError("fragmented frames not supported")
    if expect_masked is not None and masked != expect_masked:
        # RFC 6455 5.1: clients mask every frame, servers never do.
        raise WsProtocolError("masked frame from the server" if masked
                              else "unmasked frame from the client")
    length = _read_length(sock, header[1] & 0x7F, opcode)
    masking_key = _read_exact(sock, 4) if masked else None
    payload = _read_exact(sock, length) if length > 0 else b""
    return opcode, _unmask(payload, masking_key)


def _read_length(sock: socket.socket, short_length: int, opcode: int) -> int:
    """The payload length after the 7-bit field, bounded before anything is allocated."""
    length = short_length
    if length == 126:
        length = struct.unpack("!H", _read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(sock, 8))[0]
    if length > MAX_FRAME_PAYLOAD_BYTES:
        raise WsProtocolError(
            f"declared payload too large: {length} > {MAX_FRAME_PAYLOAD_BYTES}"
        )
    if opcode & 0x08 and length > 125:   # RFC 6455 5.5
        raise WsProtocolError(f"control frame payload too large: {length} > 125")
    return length


def _unmask(payload: bytes, masking_key: Optional[bytes]) -> bytes:
    """Apply the WebSocket masking key to ``payload`` when present."""
    if masking_key is None or not payload:
        return payload
    return bytes(
        payload[i] ^ masking_key[i % 4] for i in range(len(payload))
    )


def _read_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("peer closed connection")
        buf.extend(chunk)
        remaining -= len(chunk)
    return bytes(buf)
