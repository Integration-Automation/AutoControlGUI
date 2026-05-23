"""TCP viewer that receives JPEG frames and forwards input messages."""
import collections
import json
import socket
import ssl
import threading
import time as _time_module
from typing import Any, Callable, Deque, Dict, Mapping, Optional, Tuple

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
CursorCallback = Callable[[int, int], None]
ViewerCursorCallback = Callable[[str, int, int], None]
ChatCallback = Callable[[str, str], None]
ErrorCallback = Callable[[Exception], None]

_DEFAULT_AUTH_TIMEOUT_S = 60.0
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


def _extract_resume_info(payload: bytes) -> Tuple[Optional[str], Optional[float]]:
    """Pull ``(resume_token, resume_ttl)`` from an AUTH_OK JSON payload."""
    if not payload:
        return None, None
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    if not isinstance(body, dict):
        return None, None
    token = body.get("resume_token")
    ttl = body.get("resume_ttl")
    token = token if isinstance(token, str) else None
    ttl = float(ttl) if isinstance(ttl, (int, float)) else None
    return token, ttl


def _extract_codec(payload: bytes) -> Optional[str]:
    """Phase 6.8: pull the negotiated codec name from AUTH_OK JSON."""
    if not payload:
        return None
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    codec = body.get("codec")
    return codec if isinstance(codec, str) else None


class RemoteDesktopViewer:
    """Connect to a :class:`RemoteDesktopHost` and stream frames + input.

    Frames are delivered to ``on_frame`` from a background thread, so the
    callback must be quick or hand work off (e.g. via ``QMetaObject`` for
    Qt). ``send_input`` is safe to call from any thread.
    """

    def __init__(
            self, host: str, port: int, token: str,  # NOSONAR python:S107  # reason: each callback is a documented public hook; bundling further would force every caller (viewer_panel, registry, 10+ test files) through a wrapper object for marginal benefit
            on_frame: Optional[FrameCallback] = None,
            on_error: Optional[ErrorCallback] = None,
            on_audio: Optional[AudioCallback] = None,
            on_clipboard: Optional[ClipboardCallback] = None,
            on_cursor: Optional[CursorCallback] = None,
            on_viewer_cursor: Optional[ViewerCursorCallback] = None,
            on_chat: Optional[ChatCallback] = None,
            totp_code: Optional[str] = None,
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
        # Phase 4.1: when a TOTP code is supplied, the effective HMAC
        # key is "token:CODE" — host tries the same combination across
        # a ±1-step window so clock drift doesn't lock viewers out.
        self._token = (
            f"{token}:{totp_code}" if totp_code else token
        )
        self._on_frame = on_frame
        self._on_error = on_error
        self._on_audio = on_audio
        self._on_clipboard = on_clipboard
        self._on_cursor = on_cursor
        self._on_viewer_cursor = on_viewer_cursor
        self._on_chat = on_chat
        self._file_receiver: Optional[FileReceiver] = None
        self._expected_host_id = (validate_host_id(expected_host_id)
                                  if expected_host_id else None)
        self._remote_host_id: Optional[str] = None
        # Phase 6.6: AUTH_OK ships a resume token + TTL; viewer surfaces
        # them so callers can reconnect with `token=resume_token` and
        # skip both the approval popup and HMAC handshake setup cost.
        self._resume_token: Optional[str] = None
        self._resume_ttl: Optional[float] = None
        # Phase 6.8: codec negotiated in AUTH_OK; None = legacy raw JPEG.
        self._negotiated_codec: Optional[str] = None
        self._ssl_context = ssl_context
        self._server_hostname = server_hostname
        self._channel: Optional[MessageChannel] = None
        self._sock: Optional[socket.socket] = None
        self._shutdown = threading.Event()
        self._receiver: Optional[threading.Thread] = None
        self._connected = False
        # Phase 1.2: rolling counters so the GUI can render an FPS /
        # kbps overlay without reaching into private state. Lock
        # because the recv thread writes and the GUI thread reads.
        self._stats_lock = threading.Lock()
        self._stats_window: Deque[Tuple[float, int]] = collections.deque(
            maxlen=120,
        )
        self._frames_total = 0
        self._bytes_total = 0
        self._connected_at: Optional[float] = None

    @property
    def connected(self) -> bool:
        return self._connected and not self._shutdown.is_set()

    @property
    def remote_host_id(self) -> Optional[str]:
        """The host ID announced in AUTH_OK; ``None`` until handshake completes."""
        return self._remote_host_id

    @property
    def resume_token(self) -> Optional[str]:
        """Phase 6.6: host-issued reconnect token; ``None`` until AUTH_OK."""
        return self._resume_token

    @property
    def resume_ttl(self) -> Optional[float]:
        """Phase 6.6: seconds the resume token stays valid on the host."""
        return self._resume_ttl

    @property
    def negotiated_codec(self) -> Optional[str]:
        """Phase 6.8: codec name announced in AUTH_OK (``"jpeg"`` / ``"h264"`` / ``"hevc"``)."""
        return self._negotiated_codec

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
            token, ttl = _extract_resume_info(payload)
            self._resume_token = token
            self._resume_ttl = ttl
            self._negotiated_codec = _extract_codec(payload)
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
        # Phase 1.2: record the frame in the rolling stats window first
        # so even a slow on_frame callback doesn't skew the rate calc.
        self._record_frame(len(payload))
        if self._on_frame is None:
            return
        try:
            self._on_frame(payload)
        except Exception as error:  # noqa: BLE001  callback isolation
            autocontrol_logger.exception(
                "remote_desktop viewer on_frame callback raised"
            )
            self._notify_error(error)

    def _record_frame(self, byte_count: int) -> None:
        """Append a frame to the rolling stats window."""
        now = _time_module.monotonic()
        with self._stats_lock:
            self._stats_window.append((now, int(byte_count)))
            self._frames_total += 1
            self._bytes_total += int(byte_count)
            if self._connected_at is None:
                self._connected_at = now

    def stats(self) -> Dict[str, float]:
        """Phase 1.2: snapshot of FPS / kbps / totals over a 3-second window.

        ``fps`` and ``kbps`` reflect the most recent activity; ``frames``
        and ``bytes`` are session totals; ``uptime`` is wall seconds
        since the first FRAME message. Safe to call from any thread.
        """
        now = _time_module.monotonic()
        with self._stats_lock:
            window = list(self._stats_window)
            frames_total = self._frames_total
            bytes_total = self._bytes_total
            connected_at = self._connected_at
        cutoff = now - 3.0
        recent = [(ts, n) for ts, n in window if ts >= cutoff]
        if recent:
            span = max(now - recent[0][0], 0.001)
            recent_bytes = sum(n for _ts, n in recent)
            fps = len(recent) / span
            kbps = (recent_bytes * 8.0 / 1000.0) / span
        else:
            fps = 0.0
            kbps = 0.0
        uptime = (now - connected_at) if connected_at else 0.0
        return {
            "fps": round(fps, 2),
            "kbps": round(kbps, 2),
            "frames": float(frames_total),
            "bytes": float(bytes_total),
            "uptime": round(uptime, 2),
        }

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

    def send_chat(self, text: str, sender: str = "viewer") -> None:
        """Phase 5.2: send a chat message to the host."""
        if self._channel is None:
            raise RuntimeError(_NOT_CONNECTED_MESSAGE)
        if not isinstance(text, str) or not text:
            return
        import time as _time
        payload = json.dumps(
            {"sender": sender, "text": text, "ts": _time.time()},
        ).encode("utf-8")
        self._channel.send_typed(MessageType.CHAT, payload)

    def _on_recv_chat(self, payload: bytes,
                     msg_type: MessageType) -> None:
        del msg_type
        if self._on_chat is None:
            return
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(body, dict):
            return
        sender = body.get("sender", "host")
        text = body.get("text")
        if not isinstance(text, str) or not text:
            return
        try:
            self._on_chat(str(sender), text)
        except Exception:  # noqa: BLE001  callback isolation
            autocontrol_logger.exception(
                "remote_desktop viewer on_chat callback raised"
            )

    def _on_recv_cursor(self, payload: bytes,
                        msg_type: MessageType) -> None:
        del msg_type
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(body, dict):
            return
        x = body.get("x")
        y = body.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            return
        viewer_id = body.get("viewer_id")
        # Phase 5.1: a CURSOR with viewer_id is one of *other* viewers'
        # cursors echoed via MultiViewerHost; routes to a separate
        # callback so the existing on_cursor stays single-pointer.
        if viewer_id and self._on_viewer_cursor is not None:
            try:
                self._on_viewer_cursor(str(viewer_id), x, y)
            except Exception:  # noqa: BLE001  callback isolation
                autocontrol_logger.exception(
                    "remote_desktop viewer on_viewer_cursor callback raised"
                )
            return
        if self._on_cursor is None:
            return
        try:
            self._on_cursor(x, y)
        except Exception:  # noqa: BLE001  callback isolation
            autocontrol_logger.exception(
                "remote_desktop viewer on_cursor callback raised"
            )

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
    MessageType.CURSOR: RemoteDesktopViewer._on_recv_cursor,
    MessageType.CHAT: RemoteDesktopViewer._on_recv_chat,
    MessageType.PING: RemoteDesktopViewer._on_recv_ping,
}
