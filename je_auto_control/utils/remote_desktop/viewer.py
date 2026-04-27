"""TCP viewer that receives JPEG frames and forwards input messages."""
import json
import socket
import ssl
import threading
from typing import Any, Callable, Mapping, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.auth import compute_response
from je_auto_control.utils.remote_desktop.clipboard_sync import (
    ClipboardSyncError, decode as decode_clipboard, encode_image, encode_text,
)
from je_auto_control.utils.remote_desktop.file_transfer import (
    FileReceiver, FileTransferError, send_file,
)
from je_auto_control.utils.remote_desktop.host_id import validate_host_id
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError, MessageType, ProtocolError,
)
from je_auto_control.utils.remote_desktop.transport import (
    MessageChannel, TcpMessageChannel,
)

FrameCallback = Callable[[bytes], None]
AudioCallback = Callable[[bytes], None]
ClipboardCallback = Callable[[str, Any], None]
ErrorCallback = Callable[[Exception], None]

_DEFAULT_AUTH_TIMEOUT_S = 15.0
_DEFAULT_CONNECT_TIMEOUT_S = 5.0
_NOT_CONNECTED_MESSAGE = "viewer is not connected"


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
                 on_audio: Optional[AudioCallback] = None,
                 on_clipboard: Optional[ClipboardCallback] = None,
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
        self._on_audio = on_audio
        self._on_clipboard = on_clipboard
        self._file_receiver: Optional[FileReceiver] = None
        self._expected_host_id = (validate_host_id(expected_host_id)
                                  if expected_host_id else None)
        self._remote_host_id: Optional[str] = None
        self._ssl_context = ssl_context
        self._server_hostname = server_hostname
        self._channel: Optional[MessageChannel] = None
        self._sock: Optional[socket.socket] = None
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
        # If the caller explicitly asked for a longer connect budget,
        # honor it for the handshake too — otherwise a slow remote (CI
        # runners, high-latency links) trips the 5 s default before the
        # caller's window expires.
        raw_sock.settimeout(max(_DEFAULT_AUTH_TIMEOUT_S, float(timeout)))
        try:
            sock = self._maybe_wrap_tls(raw_sock)
            channel = self._build_channel(sock)
            self._handshake(channel)
        except (AuthenticationError, ProtocolError, OSError):
            try:
                raw_sock.close()
            except OSError:
                pass
            raise
        channel.settimeout(None)
        self._sock = sock
        self._channel = channel
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

    def _build_channel(self, sock: socket.socket) -> MessageChannel:
        """Hook for transports: TCP wraps directly, WS overrides this."""
        return TcpMessageChannel(sock)

    def disconnect(self, timeout: float = 2.0) -> None:
        """Close the connection and join the receiver thread."""
        self._shutdown.set()
        channel = self._channel
        if channel is not None:
            channel.close()
        self._sock = None
        self._channel = None
        receiver = self._receiver
        if receiver is not None:
            receiver.join(timeout=timeout)
        self._receiver = None
        self._connected = False

    def send_input(self, action: Mapping[str, Any]) -> None:
        """JSON-encode ``action`` and forward it as an INPUT message."""
        if not self._connected or self._channel is None:
            raise ConnectionError(_NOT_CONNECTED_MESSAGE)
        if not isinstance(action, Mapping):
            raise TypeError("action must be a mapping")
        payload = json.dumps(dict(action), ensure_ascii=False).encode("utf-8")
        self._channel.send_typed(MessageType.INPUT, payload)

    def send_ping(self) -> None:
        """Send a no-op PING message; the host treats it as liveness."""
        if not self._connected or self._channel is None:
            raise ConnectionError(_NOT_CONNECTED_MESSAGE)
        self._channel.send_typed(MessageType.PING, b"")

    def send_clipboard_text(self, text: str) -> None:
        """Push ``text`` onto the host's clipboard."""
        if not self._connected or self._channel is None:
            raise ConnectionError(_NOT_CONNECTED_MESSAGE)
        self._channel.send_typed(MessageType.CLIPBOARD, encode_text(text))

    def send_clipboard_image(self, png_bytes: bytes) -> None:
        """Push a PNG image onto the host's clipboard."""
        if not self._connected or self._channel is None:
            raise ConnectionError(_NOT_CONNECTED_MESSAGE)
        self._channel.send_typed(MessageType.CLIPBOARD, encode_image(png_bytes))

    def set_file_receiver(self, receiver: FileReceiver) -> None:
        """Replace the default ``FileReceiver`` used for incoming files."""
        self._file_receiver = receiver

    def _ensure_file_receiver(self) -> FileReceiver:
        if self._file_receiver is None:
            self._file_receiver = FileReceiver()
        return self._file_receiver

    def send_file(self, source_path: str, dest_path: str,
                  on_progress=None):
        """Stream ``source_path`` to ``dest_path`` on the host.

        Returns the :class:`FileSendResult`. Synchronous: callers wanting
        a non-blocking upload should run this in a worker thread.
        """
        if not self._connected or self._channel is None:
            raise ConnectionError(_NOT_CONNECTED_MESSAGE)
        return send_file(self._channel, source_path, dest_path,
                         on_progress=on_progress)

    def _handle_file_payload(self, msg_type: MessageType,
                             payload: bytes) -> None:
        receiver = self._ensure_file_receiver()
        try:
            if msg_type is MessageType.FILE_BEGIN:
                receiver.handle_begin(payload)
            elif msg_type is MessageType.FILE_CHUNK:
                receiver.handle_chunk(payload)
            elif msg_type is MessageType.FILE_END:
                receiver.handle_end(payload)
        except FileTransferError as error:
            autocontrol_logger.info(
                "remote_desktop viewer bad file message: %r", error,
            )

    def _handle_clipboard_payload(self, payload: bytes) -> None:
        try:
            kind, data = decode_clipboard(payload)
        except ClipboardSyncError as error:
            autocontrol_logger.info(
                "remote_desktop viewer bad CLIPBOARD: %r", error,
            )
            return
        if self._on_clipboard is not None:
            try:
                self._on_clipboard(kind, data)
            except Exception:  # noqa: BLE001
                autocontrol_logger.exception(
                    "remote_desktop viewer on_clipboard callback raised"
                )

    # context manager ----------------------------------------------------

    def __enter__(self) -> "RemoteDesktopViewer":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    # internals ----------------------------------------------------------

    def _handshake(self, channel: MessageChannel) -> None:
        msg_type, payload = channel.read_typed()
        if msg_type is not MessageType.AUTH_CHALLENGE:
            raise AuthenticationError(
                f"expected AUTH_CHALLENGE, got {msg_type.name}"
            )
        response = compute_response(self._token, payload)
        channel.send_typed(MessageType.AUTH_RESPONSE, response)
        msg_type, payload = channel.read_typed()
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
        channel = self._channel
        if channel is None:
            return
        try:
            while not self._shutdown.is_set():
                if not self._read_and_dispatch(channel):
                    return
        finally:
            self._connected = False

    def _read_and_dispatch(self, channel: MessageChannel) -> bool:
        """Read one typed message and dispatch it; return False on disconnect."""
        try:
            msg_type, payload = channel.read_typed()
        except (OSError, ProtocolError) as error:
            self._notify_error(error)
            return False
        handler = _RECV_HANDLERS.get(msg_type)
        if handler is None:
            autocontrol_logger.info(
                "remote_desktop viewer ignoring %s message", msg_type.name,
            )
            return True
        handler(self, payload, msg_type)
        return True

    # --- per-message dispatch helpers ---------------------------------

    def _on_recv_frame(self, payload: bytes,
                       msg_type: MessageType) -> None:
        del msg_type
        if self._on_frame is None:
            return
        try:
            self._on_frame(payload)
        except Exception as error:  # noqa: BLE001  callback isolation
            autocontrol_logger.exception(
                "remote_desktop viewer on_frame callback raised"
            )
            self._notify_error(error)

    def _on_recv_audio(self, payload: bytes,
                       msg_type: MessageType) -> None:
        del msg_type
        if self._on_audio is None:
            return
        try:
            self._on_audio(payload)
        except Exception:  # noqa: BLE001
            autocontrol_logger.exception(
                "remote_desktop viewer on_audio callback raised"
            )

    def _on_recv_clipboard(self, payload: bytes,
                           msg_type: MessageType) -> None:
        del msg_type
        self._handle_clipboard_payload(payload)

    def _on_recv_file(self, payload: bytes,
                      msg_type: MessageType) -> None:
        self._handle_file_payload(msg_type, payload)

    def _on_recv_ping(self, payload: bytes,
                      msg_type: MessageType) -> None:
        del payload, msg_type

    def _notify_error(self, error: BaseException) -> None:
        if self._shutdown.is_set() or self._on_error is None:
            return
        try:
            self._on_error(error)
        except Exception:  # noqa: BLE001  callback isolation
            autocontrol_logger.exception(
                "remote_desktop viewer on_error callback raised"
            )


_RECV_HANDLERS = {
    MessageType.FRAME: RemoteDesktopViewer._on_recv_frame,
    MessageType.AUDIO: RemoteDesktopViewer._on_recv_audio,
    MessageType.CLIPBOARD: RemoteDesktopViewer._on_recv_clipboard,
    MessageType.FILE_BEGIN: RemoteDesktopViewer._on_recv_file,
    MessageType.FILE_CHUNK: RemoteDesktopViewer._on_recv_file,
    MessageType.FILE_END: RemoteDesktopViewer._on_recv_file,
    MessageType.PING: RemoteDesktopViewer._on_recv_ping,
}
