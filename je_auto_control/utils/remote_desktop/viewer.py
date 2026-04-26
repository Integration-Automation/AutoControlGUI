"""TCP viewer that receives JPEG frames and forwards input messages."""
import json
import socket
import ssl
import threading
from typing import Any, Callable, Mapping, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.auth import compute_response
from je_auto_control.utils.remote_desktop.host_id import validate_host_id
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError, MessageType, ProtocolError,
    encode_frame, read_message,
)

FrameCallback = Callable[[bytes], None]
ErrorCallback = Callable[[Exception], None]

_DEFAULT_AUTH_TIMEOUT_S = 5.0
_DEFAULT_CONNECT_TIMEOUT_S = 5.0


def _extract_host_id(payload: bytes) -> Optional[str]:
    """Pull ``host_id`` out of an AUTH_OK payload (JSON or empty)."""
    if not payload:
        return None
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    value = body.get("host_id") if isinstance(body, dict) else None
    return value if isinstance(value, str) else None


class RemoteDesktopViewer:
    """Connect to a :class:`RemoteDesktopHost` and stream frames + input.

    Frames are delivered to ``on_frame`` from a background thread, so the
    callback must be quick or hand work off (e.g. via ``QMetaObject`` for
    Qt). ``send_input`` is safe to call from any thread.
    """

    def __init__(self, host: str, port: int, token: str,
                 on_frame: Optional[FrameCallback] = None,
                 on_error: Optional[ErrorCallback] = None,
                 expected_host_id: Optional[str] = None,
                 ssl_context: Optional[ssl.SSLContext] = None,
                 server_hostname: Optional[str] = None,
                 ) -> None:
        if not isinstance(host, str) or not host:
            raise ValueError("host must be a non-empty string")
        if not isinstance(token, str) or not token:
            raise ValueError("token must be a non-empty string")
        self._host = host
        self._port = int(port)
        self._token = token
        self._on_frame = on_frame
        self._on_error = on_error
        self._expected_host_id = (validate_host_id(expected_host_id)
                                  if expected_host_id else None)
        self._remote_host_id: Optional[str] = None
        self._ssl_context = ssl_context
        self._server_hostname = server_hostname
        self._sock: Optional[socket.socket] = None
        self._send_lock = threading.Lock()
        self._shutdown = threading.Event()
        self._receiver: Optional[threading.Thread] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and not self._shutdown.is_set()

    @property
    def remote_host_id(self) -> Optional[str]:
        """The host ID announced in AUTH_OK; ``None`` until handshake completes."""
        return self._remote_host_id

    def connect(self, timeout: float = _DEFAULT_CONNECT_TIMEOUT_S) -> None:
        """Open the (optionally TLS) connection and complete the auth handshake.

        Spawns a receiver thread on success. Raises
        :class:`AuthenticationError` if the handshake fails.
        """
        if self._connected:
            return
        raw_sock = socket.create_connection(
            (self._host, self._port), timeout=timeout,
        )
        raw_sock.settimeout(_DEFAULT_AUTH_TIMEOUT_S)
        try:
            sock = self._maybe_wrap_tls(raw_sock)
            self._handshake(sock)
        except (AuthenticationError, ProtocolError, OSError, ssl.SSLError):
            try:
                raw_sock.close()
            except OSError:
                pass
            raise
        sock.settimeout(None)
        self._sock = sock
        self._shutdown.clear()
        self._connected = True
        self._receiver = threading.Thread(
            target=self._recv_loop, name="rd-viewer", daemon=True,
        )
        self._receiver.start()

    def _maybe_wrap_tls(self, raw_sock: socket.socket) -> socket.socket:
        """Return a TLS-wrapped socket when an ssl_context was configured."""
        if self._ssl_context is None:
            return raw_sock
        hostname = self._server_hostname or self._host
        if (self._ssl_context.check_hostname is False
                and self._ssl_context.verify_mode == ssl.CERT_NONE):
            # ``wrap_socket`` rejects server_hostname when verification is off.
            hostname = None
        return self._ssl_context.wrap_socket(
            raw_sock, server_hostname=hostname,
        )

    def disconnect(self, timeout: float = 2.0) -> None:
        """Close the connection and join the receiver thread."""
        self._shutdown.set()
        sock = self._sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self._sock = None
        receiver = self._receiver
        if receiver is not None:
            receiver.join(timeout=timeout)
        self._receiver = None
        self._connected = False

    def send_input(self, action: Mapping[str, Any]) -> None:
        """JSON-encode ``action`` and forward it as an INPUT message."""
        if not self._connected or self._sock is None:
            raise ConnectionError("viewer is not connected")
        if not isinstance(action, Mapping):
            raise TypeError("action must be a mapping")
        payload = json.dumps(dict(action), ensure_ascii=False).encode("utf-8")
        data = encode_frame(MessageType.INPUT, payload)
        with self._send_lock:
            self._sock.sendall(data)

    def send_ping(self) -> None:
        """Send a no-op PING message; the host treats it as liveness."""
        if not self._connected or self._sock is None:
            raise ConnectionError("viewer is not connected")
        data = encode_frame(MessageType.PING, b"")
        with self._send_lock:
            self._sock.sendall(data)

    # context manager ----------------------------------------------------

    def __enter__(self) -> "RemoteDesktopViewer":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    # internals ----------------------------------------------------------

    def _handshake(self, sock: socket.socket) -> None:
        msg_type, payload = read_message(sock)
        if msg_type is not MessageType.AUTH_CHALLENGE:
            raise AuthenticationError(
                f"expected AUTH_CHALLENGE, got {msg_type.name}"
            )
        response = compute_response(self._token, payload)
        sock.sendall(encode_frame(MessageType.AUTH_RESPONSE, response))
        msg_type, payload = read_message(sock)
        if msg_type is MessageType.AUTH_OK:
            self._remote_host_id = _extract_host_id(payload)
            self._verify_host_id(self._remote_host_id)
            return
        if msg_type is MessageType.AUTH_FAIL:
            raise AuthenticationError(
                payload.decode("utf-8", errors="replace") or "auth rejected"
            )
        raise AuthenticationError(
            f"unexpected handshake reply {msg_type.name}"
        )

    def _verify_host_id(self, announced: Optional[str]) -> None:
        """Reject the connection when the server's ID does not match expectation."""
        if self._expected_host_id is None:
            return
        if announced != self._expected_host_id:
            raise AuthenticationError(
                f"host_id mismatch: expected {self._expected_host_id}, "
                f"got {announced!r}"
            )

    def _recv_loop(self) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            while not self._shutdown.is_set():
                try:
                    msg_type, payload = read_message(sock)
                except (OSError, ConnectionError, ProtocolError) as error:
                    if not self._shutdown.is_set() and self._on_error is not None:
                        try:
                            self._on_error(error)
                        except Exception:  # noqa: BLE001  # callback isolation
                            autocontrol_logger.exception(
                                "remote_desktop viewer on_error callback raised"
                            )
                    return
                if msg_type is MessageType.FRAME:
                    if self._on_frame is not None:
                        try:
                            self._on_frame(payload)
                        except Exception as error:  # noqa: BLE001
                            autocontrol_logger.exception(
                                "remote_desktop viewer on_frame callback raised"
                            )
                            if self._on_error is not None:
                                try:
                                    self._on_error(error)
                                except Exception:  # noqa: BLE001
                                    pass
                    continue
                if msg_type is MessageType.PING:
                    continue
                autocontrol_logger.info(
                    "remote_desktop viewer ignoring %s message", msg_type.name,
                )
        finally:
            self._connected = False
