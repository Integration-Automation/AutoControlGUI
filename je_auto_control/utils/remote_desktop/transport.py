"""Pluggable typed-message transport for the remote-desktop protocol.

The host and viewer always exchange the same typed messages
(``MessageType`` from :mod:`protocol`), but the wire layer can be either
the original raw-TCP framing or WebSocket binary frames. ``MessageChannel``
hides that distinction so the rest of the codebase deals with
``send_typed`` / ``read_typed`` only.
"""
import socket
import threading
from typing import Tuple

from je_auto_control.utils.remote_desktop.protocol import (
    HEADER_SIZE, MessageType, ProtocolError,
    decode_frame_header, encode_frame, read_message,
)
from je_auto_control.utils.remote_desktop.ws_protocol import (
    recv_message as ws_recv_message,
    send_binary as ws_send_binary,
    send_close as ws_send_close,
)


class MessageChannel:
    """Abstract bidirectional typed-message endpoint."""

    def send_typed(self, message_type: MessageType, payload: bytes) -> None:
        raise NotImplementedError

    def read_typed(self) -> Tuple[MessageType, bytes]:
        raise NotImplementedError

    def settimeout(self, timeout) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class TcpMessageChannel(MessageChannel):
    """Original transport: each typed message is one length-prefixed frame."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._send_lock = threading.Lock()

    def send_typed(self, message_type: MessageType, payload: bytes) -> None:
        data = encode_frame(message_type, payload)
        with self._send_lock:
            self._sock.sendall(data)

    def read_typed(self) -> Tuple[MessageType, bytes]:
        return read_message(self._sock)

    def settimeout(self, timeout) -> None:
        self._sock.settimeout(timeout)

    def close(self) -> None:
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass

    @property
    def sock(self) -> socket.socket:
        return self._sock


class WsMessageChannel(MessageChannel):
    """WebSocket transport: each WS BINARY frame carries one typed message.

    The WS payload is the existing typed-frame encoding (magic + type +
    length + body), so :func:`decode_frame_header` and :func:`encode_frame`
    are reused unchanged. ``mask_outgoing`` follows RFC 6455: clients must
    mask, servers must not.
    """

    def __init__(self, sock: socket.socket, mask_outgoing: bool) -> None:
        self._sock = sock
        self._mask = bool(mask_outgoing)
        self._send_lock = threading.Lock()

    def send_typed(self, message_type: MessageType, payload: bytes) -> None:
        data = encode_frame(message_type, payload)
        with self._send_lock:
            ws_send_binary(self._sock, data, mask=self._mask)

    def read_typed(self) -> Tuple[MessageType, bytes]:
        ws_payload = ws_recv_message(self._sock)
        if len(ws_payload) < HEADER_SIZE:
            raise ProtocolError("WS payload too short to contain typed header")
        msg_type, length = decode_frame_header(ws_payload[:HEADER_SIZE])
        body = ws_payload[HEADER_SIZE:HEADER_SIZE + length]
        if len(body) != length:
            raise ProtocolError(
                f"declared length {length} but ws payload had {len(body)}"
            )
        return msg_type, body

    def settimeout(self, timeout) -> None:
        self._sock.settimeout(timeout)

    def close(self) -> None:
        try:
            ws_send_close(self._sock, mask=self._mask)
        except OSError:
            pass
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass

    @property
    def sock(self) -> socket.socket:
        return self._sock
