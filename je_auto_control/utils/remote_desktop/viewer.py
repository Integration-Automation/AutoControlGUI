"""TCP viewer that receives JPEG frames and forwards input messages."""
import json
import socket
import threading
from typing import Any, Callable, Mapping, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.auth import compute_response
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError, MessageType, ProtocolError,
    encode_frame, read_message,
)

FrameCallback = Callable[[bytes], None]
ErrorCallback = Callable[[Exception], None]

_DEFAULT_AUTH_TIMEOUT_S = 5.0
_DEFAULT_CONNECT_TIMEOUT_S = 5.0


class RemoteDesktopViewer:
    """Connect to a :class:`RemoteDesktopHost` and stream frames + input.

    Frames are delivered to ``on_frame`` from a background thread, so the
    callback must be quick or hand work off (e.g. via ``QMetaObject`` for
    Qt). ``send_input`` is safe to call from any thread.
    """

    def __init__(self, host: str, port: int, token: str,
                 on_frame: Optional[FrameCallback] = None,
                 on_error: Optional[ErrorCallback] = None,
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
        self._sock: Optional[socket.socket] = None
        self._send_lock = threading.Lock()
        self._shutdown = threading.Event()
        self._receiver: Optional[threading.Thread] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and not self._shutdown.is_set()

    def connect(self, timeout: float = _DEFAULT_CONNECT_TIMEOUT_S) -> None:
        """Open the TCP connection and complete the auth handshake.

        Spawns a receiver thread on success. Raises
        :class:`AuthenticationError` if the handshake fails.
        """
        if self._connected:
            return
        sock = socket.create_connection(
            (self._host, self._port), timeout=timeout,
        )
        sock.settimeout(_DEFAULT_AUTH_TIMEOUT_S)
        try:
            self._handshake(sock)
        except (AuthenticationError, ProtocolError, OSError):
            try:
                sock.close()
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
            return
        if msg_type is MessageType.AUTH_FAIL:
            raise AuthenticationError(
                payload.decode("utf-8", errors="replace") or "auth rejected"
            )
        raise AuthenticationError(
            f"unexpected handshake reply {msg_type.name}"
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
