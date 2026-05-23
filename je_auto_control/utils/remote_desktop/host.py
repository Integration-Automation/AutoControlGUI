"""TCP host that streams JPEG frames and applies viewer input."""
import collections
import json
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Sequence

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.audio import (
    AudioCapture, AudioCaptureConfig,
)
from je_auto_control.utils.remote_desktop.auth import (
    make_nonce, verify_response,
)
from je_auto_control.utils.remote_desktop.clipboard_sync import (
    ClipboardSyncError, decode as decode_clipboard, encode_image, encode_text,
)
from je_auto_control.utils.remote_desktop.file_transfer import (
    FileReceiver, FileTransferError, send_file,
)
from je_auto_control.utils.remote_desktop.host_id import (
    load_or_create_host_id, validate_host_id,
)
from je_auto_control.utils.remote_desktop.input_dispatch import (
    InputDispatchError, dispatch_input,
)
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError, MessageType, ProtocolError,
)
from je_auto_control.utils.remote_desktop.resume_tokens import (
    ResumeTokenStore,
)
from je_auto_control.utils.remote_desktop.video_codec import (
    CODEC_JPEG, CodecProvider, JpegPassthrough, codec_tag,
)
from je_auto_control.utils.remote_desktop.transport import (
    MessageChannel, TcpMessageChannel,
)

FrameProvider = Callable[[], bytes]
InputDispatcher = Callable[[Mapping[str, Any]], Any]
CursorProvider = Callable[[], Optional[Sequence[int]]]
"""Return ``(x, y)`` in host screen coordinates, or ``None`` to skip a tick."""

_CURSOR_POLL_INTERVAL_S = 1.0 / 30.0  # 30 Hz: smooth, low CPU on idle.


@dataclass(frozen=True)
class PendingViewer:
    """Snapshot of an authenticated viewer awaiting host approval.

    Passed to the ``on_pending_viewer`` callback after the HMAC handshake
    succeeds but before the host starts streaming frames. The callback's
    return value is interpreted as:

    * ``True``  / ``"full"``      → admit with full control
    * ``"view_only"``             → admit, but drop incoming INPUT messages
    * ``False`` / ``None`` / etc. → reject
    """
    address: tuple
    host_id: str
    transport: str = "tcp"


PendingViewerCallback = Callable[[PendingViewer], Any]
"""Callback signature: see :class:`PendingViewer` for return value semantics."""


PERMISSION_FULL = "full"
PERMISSION_VIEW_ONLY = "view_only"
PERMISSION_DENIED = "denied"


def _interpret_approval(result: Any) -> str:
    """Map an approval-callback return value to a permission string.

    Backward compatibility: any truthy value other than the literal
    ``"view_only"`` / ``"denied"`` strings is treated as full-control
    admit. Falsy values are denied.
    """
    if result == PERMISSION_VIEW_ONLY:
        return PERMISSION_VIEW_ONLY
    if result == PERMISSION_DENIED or not result:
        return PERMISSION_DENIED
    return PERMISSION_FULL


_AUTH_TIMEOUT_S = 60.0
_DEFAULT_QUALITY = 70
_FILE_MSG_TYPES = frozenset({
    MessageType.FILE_BEGIN, MessageType.FILE_CHUNK, MessageType.FILE_END,
})


def _candidate_totp_codes(secret: str):
    """Yield TOTP codes within ±1 step of the current 30-second window."""
    from je_auto_control.utils.remote_desktop.totp import generate_code
    now = time.time()
    for delta in (-1, 0, 1):
        yield generate_code(secret, at=now + (delta * 30.0))


def _validate_host_args(token: str, fps: float, quality: int) -> None:
    """Throw early on bad constructor args so the host never starts broken."""
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    if fps <= 0:
        raise ValueError("fps must be positive")
    if not 1 <= quality <= 95:
        raise ValueError("quality must be in [1, 95]")


def list_host_monitors() -> List[Dict[str, Any]]:
    """Headless helper: return every monitor's geometry.

    Index 0 spans all monitors (the ``mss`` convention). Returns an
    empty list if ``mss`` is not installed, so GUI callers can show a
    disabled control instead of crashing.
    """
    try:
        import mss
    except ImportError:
        return []
    with mss.mss() as sct:
        return [
            {
                "index": index, "left": int(monitor["left"]),
                "top": int(monitor["top"]),
                "width": int(monitor["width"]),
                "height": int(monitor["height"]),
                "is_combined": index == 0,
            }
            for index, monitor in enumerate(sct.monitors)
        ]


def _resolve_monitor_region(
        monitor_index: int) -> Optional[Sequence[int]]:
    """Map an ``mss`` monitor index to ``(x, y, width, height)``.

    Returns ``None`` (full-screen capture fallback) when ``mss`` is
    not available so a stock install still works.
    """
    try:
        import mss
    except ImportError:
        autocontrol_logger.warning(
            "remote_desktop monitor_index=%d ignored: mss not installed",
            monitor_index,
        )
        return None
    with mss.mss() as sct:
        if monitor_index < 0 or monitor_index >= len(sct.monitors):
            raise ValueError(
                f"monitor_index {monitor_index} out of range "
                f"(0..{len(sct.monitors) - 1})"
            )
        mon = sct.monitors[monitor_index]
        return (
            int(mon["left"]), int(mon["top"]),
            int(mon["width"]), int(mon["height"]),
        )


def _compile_ip_allowlist(
        entries: Optional[Sequence[str]]) -> Optional[List[Any]]:
    """Pre-parse ``entries`` into ``ip_address`` / ``ip_network`` objects.

    ``None`` or an empty list → no filtering (allow all). Entries are
    plain IPs (``"192.168.1.10"``) or CIDR ranges (``"10.0.0.0/8"``);
    unparseable entries are dropped with a warning so a typo doesn't
    silently broaden access.
    """
    if not entries:
        return None
    import ipaddress
    compiled: List[Any] = []
    for entry in entries:
        text = str(entry).strip()
        if not text:
            continue
        try:
            if "/" in text:
                compiled.append(ipaddress.ip_network(text, strict=False))
            else:
                compiled.append(ipaddress.ip_address(text))
        except ValueError:
            autocontrol_logger.warning(
                "remote_desktop ip_allowlist entry rejected: %r", text,
            )
    return compiled or None


def _ip_in_allowlist(allowlist: Optional[List[Any]], peer_ip: str) -> bool:
    """Return True when ``peer_ip`` matches any allowlist entry (or no list)."""
    if not allowlist:
        return True
    import ipaddress
    try:
        addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    for entry in allowlist:
        if isinstance(entry, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            if addr in entry:
                return True
        elif entry == addr:
            return True
    return False


def _resolve_cursor_provider(
        explicit: Optional[CursorProvider],
        enabled: bool) -> Optional[CursorProvider]:
    """Pick the cursor provider — explicit > default > disabled."""
    if explicit is not None:
        return explicit
    return _default_cursor_provider() if enabled else None


def _default_cursor_provider() -> CursorProvider:
    """Build a cursor-position poller using the project's mouse wrapper.

    The wrapper is imported lazily inside the closure so importing this
    module on platforms where mouse capture is unavailable does not
    blow up. Returns ``None`` on read failures so the broadcast loop
    silently skips the tick instead of crashing the host.
    """
    def provide() -> Optional[Sequence[int]]:
        try:
            from je_auto_control.wrapper.auto_control_mouse import (
                get_mouse_position,
            )
        except ImportError:
            return None
        try:
            return get_mouse_position()
        except (OSError, RuntimeError, AttributeError):
            return None
    return provide


def _default_frame_provider(region: Optional[Sequence[int]] = None,
                            quality: int = _DEFAULT_QUALITY) -> FrameProvider:
    """Build a JPEG frame producer using PIL.ImageGrab."""
    def provide() -> bytes:
        from PIL import ImageGrab  # local import: not needed for unit tests
        if region is not None:
            x, y, width, height = (int(v) for v in region)
            bbox = (x, y, x + width, y + height)
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
        else:
            image = ImageGrab.grab(all_screens=True)
        if image.mode != "RGB":
            image = image.convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=int(quality))
        return buffer.getvalue()
    return provide


class _ClientHandler:
    """Per-connection auth + input-receive + frame-send state."""

    _AUDIO_QUEUE_MAXLEN = 50  # ~2.5 s of buffered chunks at 50 ms each

    def __init__(self, host: "RemoteDesktopHost",
                 channel: MessageChannel, address) -> None:
        self._host = host
        self._channel = channel
        self._address = address
        self._shutdown = threading.Event()
        self._sender_thread: Optional[threading.Thread] = None
        self._receiver_thread: Optional[threading.Thread] = None
        self._audio_queue: Deque[bytes] = collections.deque(
            maxlen=self._AUDIO_QUEUE_MAXLEN,
        )
        self._audio_lock = threading.Lock()
        self._audio_event = threading.Event()
        self._audio_sender_thread: Optional[threading.Thread] = None
        self.authenticated = False
        # Phase 5.3: per-client permission set by the approval callback.
        # Default is full control so legacy callers (no callback) keep
        # the prior behaviour.
        self.permission = PERMISSION_FULL

    @property
    def address(self):
        return self._address

    def start(self) -> None:
        """Run auth (with optional host approval), then start the loops."""
        try:
            self._authenticate()
        except (AuthenticationError, ProtocolError, OSError) as error:
            autocontrol_logger.info(
                "remote_desktop client %s rejected: %r", self._address, error,
            )
            self._close()
            return
        self.authenticated = True
        # Seed the viewer with the latest cursor position so the overlay
        # appears immediately instead of waiting for the next change.
        self._host._send_initial_cursor(self)
        # Phase 2.3: motion-aware capture means seq only advances on
        # change, so a viewer that joins a static desktop would
        # otherwise wait until the host moves. Push the latest frame
        # immediately so the connect screen has something to show.
        self._send_initial_frame()
        self._sender_thread = threading.Thread(
            target=self._send_loop, name="rd-sender", daemon=True,
        )
        self._receiver_thread = threading.Thread(
            target=self._recv_loop, name="rd-recv", daemon=True,
        )
        self._sender_thread.start()
        self._receiver_thread.start()
        if self._host._audio_config.enabled:
            self._audio_sender_thread = threading.Thread(
                target=self._audio_send_loop, name="rd-audio", daemon=True,
            )
            self._audio_sender_thread.start()

    def _send_initial_frame(self) -> None:
        """Forward the most recent encoded frame so new clients aren't blank.

        Motion-dedup in :meth:`_capture_loop` means a static desktop
        only bumps ``_latest_seq`` once; replaying that frame to the
        new client keeps them from sitting on a black popup until the
        host moves something.
        """
        with self._host._frame_cond:
            frame = self._host._latest_frame
        if frame is None:
            return
        try:
            self._channel.send_typed(MessageType.FRAME, frame)
        except OSError:
            pass

    def push_audio(self, chunk: bytes) -> None:
        """Enqueue a PCM chunk for delivery; oldest dropped if queue is full."""
        if self._shutdown.is_set() or not self.authenticated:
            return
        with self._audio_lock:
            self._audio_queue.append(chunk)
        self._audio_event.set()

    def stop(self) -> None:
        """Signal threads and close the socket."""
        self._shutdown.set()
        with self._host._frame_cond:
            self._host._frame_cond.notify_all()
        self._audio_event.set()
        self._close()

    def _resolve_permission(self) -> str:
        """Run the host's optional approval callback after token auth.

        Returns one of :data:`PERMISSION_FULL` / :data:`PERMISSION_VIEW_ONLY`
        (admit) or :data:`PERMISSION_DENIED` (reject). The caller is
        expected to send ``AUTH_FAIL`` and raise on denial — keeping
        that wire-level handling inside :meth:`_authenticate` so the
        viewer sees the rejection before it has a chance to flip into
        the post-handshake state where ``AUTH_FAIL`` is ignored.
        """
        callback = self._host._on_pending_viewer
        if callback is None:
            return PERMISSION_FULL
        pending = PendingViewer(
            address=tuple(self._address) if self._address else (),
            host_id=self._host.host_id,
            transport=self._host._transport_name(),
        )
        try:
            return _interpret_approval(callback(pending))
        except (RuntimeError, ValueError, TypeError) as error:
            autocontrol_logger.info(
                "remote_desktop approval callback raised for %s: %r",
                self._address, error,
            )
            return PERMISSION_DENIED

    def _authenticate(self) -> None:
        nonce = make_nonce()
        self._channel.settimeout(_AUTH_TIMEOUT_S)
        self._channel.send_typed(MessageType.AUTH_CHALLENGE, nonce)
        msg_type, payload = self._channel.read_typed()
        if msg_type is not MessageType.AUTH_RESPONSE:
            self._channel.send_typed(MessageType.AUTH_FAIL,
                                     b"expected AUTH_RESPONSE")
            raise AuthenticationError(
                f"expected AUTH_RESPONSE, got {msg_type.name}"
            )
        # Phase 6.6: a viewer reconnecting with a valid resume token
        # signs with that token directly — host short-circuits the
        # approval popup and reuses the saved permission.
        resumed = self._host._try_consume_resume(nonce, payload)
        if resumed is not None:
            self.permission = resumed
        else:
            if not self._host._verify_token(nonce, payload):
                self._channel.send_typed(MessageType.AUTH_FAIL, b"bad token")
                raise AuthenticationError("bad token")
            # Host operator gates the session *before* AUTH_OK so the
            # viewer surfaces the rejection as an AuthenticationError
            # instead of connecting and then mysteriously disconnecting.
            permission = self._resolve_permission()
            if permission == PERMISSION_DENIED:
                self._channel.send_typed(
                    MessageType.AUTH_FAIL, b"rejected by host",
                )
                raise AuthenticationError("rejected by host")
            self.permission = permission
        # Issue a fresh resume token so the viewer can reconnect
        # within the store's TTL without the approval popup.
        resume_token = self._host._resume_store.issue(self.permission)
        ok_payload = json.dumps(
            {"host_id": self._host.host_id,
             "resume_token": resume_token,
             "resume_ttl": self._host._resume_store.ttl,
             "codec": self._host._codec_provider.name},
            ensure_ascii=False,
        ).encode("utf-8")
        self._channel.send_typed(MessageType.AUTH_OK, ok_payload)
        self._channel.settimeout(None)

    def _send_loop(self) -> None:
        last_sent = 0
        while not self._shutdown.is_set():
            with self._host._frame_cond:
                while (not self._shutdown.is_set()
                       and self._host._latest_seq <= last_sent):
                    self._host._frame_cond.wait(timeout=0.5)
                if self._shutdown.is_set():
                    return
                frame = self._host._latest_frame
                seq = self._host._latest_seq
            if frame is None:
                continue
            try:
                self._channel.send_typed(MessageType.FRAME, frame)
            except OSError as error:
                autocontrol_logger.info(
                    "remote_desktop send to %s failed: %r",
                    self._address, error,
                )
                self.stop()
                return
            last_sent = seq

    def _audio_send_loop(self) -> None:
        while not self._shutdown.is_set():
            self._audio_event.wait(timeout=0.5)
            if self._shutdown.is_set():
                return
            while True:
                with self._audio_lock:
                    if not self._audio_queue:
                        self._audio_event.clear()
                        break
                    chunk = self._audio_queue.popleft()
                try:
                    self._channel.send_typed(MessageType.AUDIO, chunk)
                except OSError as error:
                    autocontrol_logger.info(
                        "remote_desktop audio send to %s failed: %r",
                        self._address, error,
                    )
                    self.stop()
                    return

    def _recv_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                msg_type, payload = self._channel.read_typed()
            except (OSError, ProtocolError) as error:
                if not self._shutdown.is_set():
                    autocontrol_logger.info(
                        "remote_desktop recv from %s ended: %r",
                        self._address, error,
                    )
                self.stop()
                return
            self._route_incoming(msg_type, payload)

    def _route_incoming(self, msg_type: MessageType, payload: bytes) -> None:
        """Dispatch one received message to the matching handler."""
        if msg_type is MessageType.PING:
            return
        if msg_type is MessageType.INPUT:
            # Phase 5.3: drop input from view-only viewers so they can
            # watch but cannot drive the mouse / keyboard.
            if self.permission != PERMISSION_VIEW_ONLY:
                self._handle_input_payload(payload)
            return
        if msg_type is MessageType.CLIPBOARD:
            self._handle_clipboard_payload(payload)
            return
        if msg_type is MessageType.CHAT:
            self._handle_chat_payload(payload)
            return
        if msg_type in _FILE_MSG_TYPES:
            self._handle_file_payload(msg_type, payload)
            return
        autocontrol_logger.info(
            "remote_desktop unexpected msg %s from %s",
            msg_type.name, self._address,
        )

    def _handle_file_payload(self, msg_type: MessageType,
                             payload: bytes) -> None:
        receiver = self._host._ensure_file_receiver()
        try:
            if msg_type is MessageType.FILE_BEGIN:
                receiver.handle_begin(payload)
            elif msg_type is MessageType.FILE_CHUNK:
                receiver.handle_chunk(payload)
            elif msg_type is MessageType.FILE_END:
                receiver.handle_end(payload)
        except FileTransferError as error:
            autocontrol_logger.info(
                "remote_desktop bad file message from %s: %r",
                self._address, error,
            )

    def _handle_chat_payload(self, payload: bytes) -> None:
        """Forward viewer-originated chat to the host's optional callback."""
        callback = self._host._on_chat
        if callback is None:
            return
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(body, dict):
            return
        text = body.get("text")
        sender = body.get("sender", "viewer")
        if not isinstance(text, str) or not text:
            return
        try:
            callback(str(sender), text)
        except Exception:  # noqa: BLE001  callback isolation
            autocontrol_logger.exception(
                "remote_desktop on_chat callback raised"
            )

    def _handle_clipboard_payload(self, payload: bytes) -> None:
        try:
            kind, data = decode_clipboard(payload)
        except ClipboardSyncError as error:
            autocontrol_logger.info(
                "remote_desktop bad CLIPBOARD from %s: %r",
                self._address, error,
            )
            return
        try:
            self._host._apply_clipboard(kind, data)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            autocontrol_logger.warning(
                "remote_desktop clipboard apply failed for %s: %r",
                self._address, error,
            )

    def _handle_input_payload(self, payload: bytes) -> None:
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            autocontrol_logger.info(
                "remote_desktop bad INPUT from %s: %r",
                self._address, error,
            )
            return
        try:
            self._host._dispatch(message)
        except InputDispatchError as error:
            autocontrol_logger.info(
                "remote_desktop rejected INPUT from %s: %r",
                self._address, error,
            )
        except (OSError, RuntimeError, ValueError, TypeError) as error:
            autocontrol_logger.warning(
                "remote_desktop input apply failed for %s: %r",
                self._address, error,
            )

    def _close(self) -> None:
        self._channel.close()


class RemoteDesktopHost:
    """Stream the screen to authenticated viewers and apply their input.

    The instance owns three kinds of threads: one accept loop, one
    capture loop, and a sender + receiver pair per connected viewer.
    Public methods are thread-safe; ``start()`` is idempotent and
    ``stop()`` can be called from any thread.
    """

    def __init__(
            self, token: str,  # NOSONAR python:S107  # reason: each kwarg is a documented public knob; bundling further would split the API across patterns and force every existing caller (registry, host_panel, tests in 8 files) through a wrapper object for marginal benefit
            bind: str = "127.0.0.1",
            port: int = 0,
            fps: float = 10.0,
            quality: int = _DEFAULT_QUALITY,
            region: Optional[Sequence[int]] = None,
            max_clients: int = 4,
            frame_provider: Optional[FrameProvider] = None,
            input_dispatcher: Optional[InputDispatcher] = None,
            host_id: Optional[str] = None,
            ssl_context: Optional[ssl.SSLContext] = None,
            audio_config: Optional[AudioCaptureConfig] = None,
            audio_capture: Optional[Any] = None,
            on_pending_viewer: Optional[PendingViewerCallback] = None,
            cursor_provider: Optional[CursorProvider] = None,
            enable_cursor_broadcast: bool = True,
            ip_allowlist: Optional[Sequence[str]] = None,
            monitor_index: Optional[int] = None,
            single_use_tokens: Optional[Sequence[str]] = None,
            on_chat: Optional[Callable[[str, str], None]] = None,
            totp_secret: Optional[str] = None,
            codec_provider: Optional[CodecProvider] = None,
            ) -> None:
        _validate_host_args(token, fps, int(quality))
        if audio_config is None:
            audio_config = AudioCaptureConfig()
        # Phase 2.1: pick a specific monitor by index if requested and
        # the caller did not pass an explicit region.
        if region is None and monitor_index is not None:
            region = _resolve_monitor_region(monitor_index)
        self._host_id = (validate_host_id(host_id) if host_id
                         else load_or_create_host_id())
        self._token = token
        self._ssl_context = ssl_context
        self._bind = bind
        self._requested_port = int(port)
        self._period = 1.0 / float(fps)
        self._max_clients = int(max_clients)
        self._frame_provider: FrameProvider = (
            frame_provider or _default_frame_provider(region, int(quality))
        )
        self._dispatch: InputDispatcher = input_dispatcher or dispatch_input
        self._file_receiver: Optional[FileReceiver] = None
        self._audio_config = audio_config
        self._audio_capture_override = audio_capture
        self._audio_capture: Optional[AudioCapture] = None
        self._on_pending_viewer = on_pending_viewer
        self._cursor_provider: Optional[CursorProvider] = _resolve_cursor_provider(
            cursor_provider, enable_cursor_broadcast,
        )
        self._cursor_thread: Optional[threading.Thread] = None
        # Latest broadcast cursor payload, kept so newly-authenticated
        # clients can be seeded immediately instead of waiting for the
        # next position change.
        self._latest_cursor_payload: Optional[bytes] = None
        self._cursor_lock = threading.Lock()
        # Phase 4.3: parsed allowlist. None means "accept anyone".
        self._ip_allowlist: Optional[List[Any]] = _compile_ip_allowlist(
            ip_allowlist,
        )
        # Phase 4.2: extra tokens that self-destruct after a single
        # successful auth — useful for client-support workflows where
        # the host operator hands out a one-shot code that expires on
        # first use.
        self._single_use_tokens = set(single_use_tokens or ())
        self._single_use_lock = threading.Lock()
        # Phase 5.2: host-side chat callback (sender, text).
        self._on_chat = on_chat
        # Phase 4.1: TOTP secret. None disables 2FA (default).
        self._totp_secret = totp_secret
        # Phase 6.6: in-memory resume tokens — viewer reconnects within
        # the TTL skip the approval popup and re-use the saved permission.
        self._resume_store = ResumeTokenStore()
        # Phase 6.8: pluggable video codec. Default JPEG passthrough
        # keeps the wire format byte-for-byte identical to pre-6.8
        # clients; opt in to H.264 by passing an H264CodecProvider.
        self._codec_provider: CodecProvider = (
            codec_provider if codec_provider is not None else JpegPassthrough()
        )
        self._listen_sock: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._clients: List[_ClientHandler] = []
        self._clients_lock = threading.Lock()
        self._frame_cond = threading.Condition()
        self._latest_frame: Optional[bytes] = None
        self._latest_seq = 0
        self._port: int = 0

    # public API ----------------------------------------------------------

    @property
    def host_id(self) -> str:
        """The 9-digit numeric ID viewers use to verify this host."""
        return self._host_id

    @property
    def audio_enabled(self) -> bool:
        return self._audio_config.enabled and self._audio_capture is not None

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._listen_sock is not None and not self._shutdown.is_set()

    @property
    def connected_clients(self) -> int:
        with self._clients_lock:
            return sum(
                1 for client in self._clients
                if client.authenticated and not client._shutdown.is_set()
            )

    def latest_frame(self) -> Optional[bytes]:
        """Return the most recent encoded frame (JPEG bytes) or ``None``.

        Useful for a local preview pane: the GUI can poll this without
        opening a TCP connection back to the host.
        """
        with self._frame_cond:
            return self._latest_frame

    def start(self) -> None:
        """Bind, then launch accept + capture (+ cursor) threads."""
        if self.is_running:
            return
        self._shutdown.clear()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._bind, self._requested_port))
        sock.listen(self._max_clients)
        self._port = sock.getsockname()[1]
        self._listen_sock = sock
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="rd-accept", daemon=True,
        )
        self._capture_thread = threading.Thread(
            target=self._capture_loop, name="rd-capture", daemon=True,
        )
        self._accept_thread.start()
        self._capture_thread.start()
        if self._cursor_provider is not None:
            self._cursor_thread = threading.Thread(
                target=self._cursor_loop, name="rd-cursor", daemon=True,
            )
            self._cursor_thread.start()
        self._start_audio_capture()

    def stop(self, timeout: float = 2.0) -> None:
        """Tear down accept loop, capture loop, and every connected client."""
        if self._listen_sock is None:
            return
        self._shutdown.set()
        self._stop_audio_capture()
        try:
            self._listen_sock.close()
        except OSError:
            pass
        self._listen_sock = None
        with self._frame_cond:
            self._frame_cond.notify_all()
        with self._clients_lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            client.stop()
        for thread in (self._accept_thread, self._capture_thread,
                       self._cursor_thread):
            if thread is not None:
                thread.join(timeout=timeout)
        self._accept_thread = None
        self._capture_thread = None
        self._cursor_thread = None

    def _start_audio_capture(self) -> None:
        """Open the audio input stream when audio capture is enabled."""
        config = self._audio_config
        if not config.enabled:
            return
        if self._audio_capture_override is not None:
            self._audio_capture = self._audio_capture_override
            try:
                self._audio_capture.start()
            except (OSError, RuntimeError) as error:
                autocontrol_logger.warning(
                    "remote_desktop audio capture failed to start: %r", error,
                )
                self._audio_capture = None
            return
        try:
            capture = AudioCapture(
                on_block=self._broadcast_audio,
                device=config.device,
                sample_rate=config.sample_rate,
                channels=config.channels,
                block_frames=config.block_frames,
            )
            capture.start()
        except (OSError, RuntimeError) as error:
            autocontrol_logger.warning(
                "remote_desktop audio capture disabled: %r", error,
            )
            self._audio_capture = None
            return
        self._audio_capture = capture

    def _stop_audio_capture(self) -> None:
        capture = self._audio_capture
        if capture is None:
            return
        try:
            capture.stop()
        except (OSError, RuntimeError):
            pass
        self._audio_capture = None

    def _broadcast_audio(self, chunk: bytes) -> None:
        """Push a captured PCM block to every authenticated client."""
        with self._clients_lock:
            clients = [c for c in self._clients
                       if c.authenticated and not c._shutdown.is_set()]
        for client in clients:
            client.push_audio(chunk)

    def broadcast_clipboard_text(self, text: str) -> int:
        """Send a text-clipboard message to every authenticated viewer."""
        return self._broadcast_clipboard_payload(encode_text(text))

    def broadcast_clipboard_image(self, png_bytes: bytes) -> int:
        """Send a PNG image to every authenticated viewer's clipboard."""
        return self._broadcast_clipboard_payload(encode_image(png_bytes))

    def _broadcast_clipboard_payload(self, payload: bytes) -> int:
        with self._clients_lock:
            clients = [c for c in self._clients
                       if c.authenticated and not c._shutdown.is_set()]
        sent = 0
        for client in clients:
            try:
                client._channel.send_typed(MessageType.CLIPBOARD, payload)
                sent += 1
            except OSError as error:
                autocontrol_logger.info(
                    "remote_desktop clipboard send to %s failed: %r",
                    client.address, error,
                )
                client.stop()
        return sent

    def set_file_receiver(self, receiver: FileReceiver) -> None:
        """Replace the default ``FileReceiver`` (e.g. to wire progress callbacks)."""
        self._file_receiver = receiver

    def _ensure_file_receiver(self) -> FileReceiver:
        if self._file_receiver is None:
            self._file_receiver = FileReceiver()
        return self._file_receiver

    def send_file_to_viewers(self, source_path: str, dest_path: str,
                             on_progress=None) -> int:
        """Stream ``source_path`` to every authenticated viewer.

        Returns the number of viewers the transfer was attempted on.
        Each viewer gets its own ``transfer_id`` so progress callbacks
        can be demultiplexed in the GUI.
        """
        with self._clients_lock:
            clients = [c for c in self._clients
                       if c.authenticated and not c._shutdown.is_set()]
        for client in clients:
            try:
                send_file(client._channel, source_path, dest_path,
                          on_progress=on_progress)
            except (OSError, FileTransferError) as error:
                autocontrol_logger.info(
                    "remote_desktop file send to %s failed: %r",
                    client.address, error,
                )
        return len(clients)

    def _try_consume_resume(self, nonce: bytes,
                            payload: bytes) -> Optional[str]:
        """Phase 6.6: find a resume token whose HMAC matches ``payload``.

        Returns the saved permission string and removes the matching
        token from the store. Returns ``None`` when no token in the
        store signed this nonce — caller then falls back to the normal
        ``_verify_token`` path.
        """
        for token, perm in self._resume_store.list_active().items():
            if verify_response(token, nonce, payload):
                self._resume_store.remove(token)
                return perm
        return None

    def _verify_token(self, nonce: bytes, payload: bytes) -> bool:
        """Phase 4.2 + 4.1: token / single-use code / TOTP-bound token.

        When ``totp_secret`` is configured the viewer must sign with
        ``token:CODE`` where CODE is the current 6-digit TOTP. We try
        each code in a ±1-step window so a viewer that is just out of
        phase still authenticates.

        Single-use tokens are removed on first successful match so the
        same code never authenticates twice — matches the AnyDesk
        "share code" pattern for client-support flows.
        """
        if self._totp_secret is None:
            if verify_response(self._token, nonce, payload):
                return True
        else:
            for code in _candidate_totp_codes(self._totp_secret):
                if verify_response(
                        f"{self._token}:{code}", nonce, payload,
                ):
                    return True
        with self._single_use_lock:
            # No list() copy needed: ``return True`` exits before the
            # mutation could affect a subsequent iteration step.
            for code in self._single_use_tokens:
                if verify_response(code, nonce, payload):
                    self._single_use_tokens.discard(code)
                    return True
        return False

    def add_single_use_token(self, code: str) -> None:
        """Register an extra token that's consumed on first successful auth."""
        if not isinstance(code, str) or not code:
            raise ValueError("share code must be a non-empty string")
        with self._single_use_lock:
            self._single_use_tokens.add(code)

    def revoke_single_use_token(self, code: str) -> bool:
        """Remove a share code before it's used; returns True if found."""
        with self._single_use_lock:
            if code in self._single_use_tokens:
                self._single_use_tokens.discard(code)
                return True
        return False

    def _apply_clipboard(self, kind: str, data: Any) -> None:
        """Set this host's local clipboard from a decoded CLIPBOARD payload.

        Subclasses or tests may override; the default routes to the
        utils.clipboard helpers and accepts ``"text"`` / ``"image"`` kinds.
        """
        from je_auto_control.utils.clipboard.clipboard import (
            set_clipboard, set_clipboard_image,
        )
        if kind == "text":
            set_clipboard(data)
        elif kind == "image":
            set_clipboard_image(data)
        else:
            raise ValueError(f"unsupported clipboard kind: {kind!r}")

    # internals -----------------------------------------------------------

    def _cursor_loop(self) -> None:
        """Poll cursor position at ~30 Hz and push it to viewers as JSON."""
        provider = self._cursor_provider
        if provider is None:
            return
        while not self._shutdown.is_set():
            position = provider()
            if position is not None and len(position) >= 2:
                payload = json.dumps(
                    {"x": int(position[0]), "y": int(position[1]),
                     "visible": True},
                ).encode("utf-8")
                with self._cursor_lock:
                    is_new = payload != self._latest_cursor_payload
                    self._latest_cursor_payload = payload
                if is_new:
                    self._broadcast_cursor(payload)
            if self._shutdown.wait(timeout=_CURSOR_POLL_INTERVAL_S):
                return

    def _broadcast_cursor(self, payload: bytes) -> None:
        """Send a CURSOR message to every authenticated client.

        Errors per-client are swallowed — a flaky viewer should not
        kill the cursor stream to healthy peers.
        """
        with self._clients_lock:
            clients = [c for c in self._clients
                       if c.authenticated and not c._shutdown.is_set()]
        for client in clients:
            try:
                client._channel.send_typed(MessageType.CURSOR, payload)
            except OSError:
                continue

    def broadcast_viewer_cursor(self, viewer_id: str,
                                x: int, y: int) -> int:
        """Phase 5.1: relay one viewer's cursor position to every other viewer.

        Typically called by :class:`MultiViewerHost` when several
        viewers share a session so each viewer's overlay can show the
        other operators' pointers (Figma / Google Docs style). The
        viewer_id is opaque to the host — viewers use it to colour-key
        their overlay.
        """
        payload = json.dumps(
            {"x": int(x), "y": int(y), "visible": True,
             "viewer_id": str(viewer_id)},
        ).encode("utf-8")
        with self._clients_lock:
            clients = [c for c in self._clients
                       if c.authenticated and not c._shutdown.is_set()]
        sent = 0
        for client in clients:
            try:
                client._channel.send_typed(MessageType.CURSOR, payload)
                sent += 1
            except OSError:
                continue
        return sent

    def broadcast_chat(self, text: str, sender: str = "host") -> int:
        """Phase 5.2: send a chat message to every connected viewer.

        Returns the number of viewers the message was *attempted* on.
        Per-client errors are logged but do not abort the broadcast.
        """
        if not isinstance(text, str) or not text:
            return 0
        payload = json.dumps(
            {"sender": sender, "text": text, "ts": time.time()},
        ).encode("utf-8")
        with self._clients_lock:
            clients = [c for c in self._clients
                       if c.authenticated and not c._shutdown.is_set()]
        sent = 0
        for client in clients:
            try:
                client._channel.send_typed(MessageType.CHAT, payload)
                sent += 1
            except OSError as error:
                autocontrol_logger.info(
                    "remote_desktop chat send to %s failed: %r",
                    client.address, error,
                )
        return sent

    def _send_initial_cursor(self, client: "_ClientHandler") -> None:
        """Push the latest known cursor position to a fresh client.

        Sending unconditionally on auth means the viewer sees a cursor
        immediately instead of waiting up to ~1 s for the next position
        change. Safe to call when the cursor loop is disabled — we
        only send if there's a payload to send.
        """
        with self._cursor_lock:
            payload = self._latest_cursor_payload
        if payload is None:
            return
        try:
            client._channel.send_typed(MessageType.CURSOR, payload)
        except OSError:
            pass

    def _ip_allowed(self, address) -> bool:
        """Apply the Phase 4.3 allowlist; log + reject silently otherwise."""
        peer_ip = address[0] if address else ""
        if _ip_in_allowlist(self._ip_allowlist, peer_ip):
            return True
        autocontrol_logger.info(
            "remote_desktop blocked %s by ip_allowlist", peer_ip,
        )
        return False

    def _open_channel(self, client_sock: socket.socket,
                      address) -> Optional[MessageChannel]:
        """TLS-wrap + WS/TCP handshake. Closes the socket on failure."""
        wrapped = self._maybe_wrap_tls(client_sock, address)
        if wrapped is None:
            return None
        try:
            return self._build_channel(wrapped, address)
        except (OSError, RuntimeError) as error:
            autocontrol_logger.info(
                "remote_desktop channel handshake from %s failed: %r",
                address, error,
            )
            try:
                wrapped.close()
            except OSError:
                pass
            return None

    def _accept_loop(self) -> None:
        listen = self._listen_sock
        if listen is None:
            return
        listen.settimeout(0.5)
        while not self._shutdown.is_set():
            try:
                client_sock, address = listen.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if not self._ip_allowed(address):
                try:
                    client_sock.close()
                except OSError:
                    pass
                continue
            channel = self._open_channel(client_sock, address)
            if channel is None:
                continue
            handler = _ClientHandler(self, channel, address)
            with self._clients_lock:
                if len(self._clients) >= self._max_clients:
                    autocontrol_logger.info(
                        "remote_desktop dropping %s: max_clients reached",
                        address,
                    )
                    handler._close()
                    continue
                self._clients.append(handler)
            handler.start()
            self._reap_dead_clients()

    def _build_channel(self, sock: socket.socket,
                       address) -> MessageChannel:
        """Hook for transports: TCP wraps directly, WS overrides this."""
        del address
        return TcpMessageChannel(sock)

    def _transport_name(self) -> str:
        """Identifier passed to approval callbacks. WS host overrides."""
        return "tcp"

    def _maybe_wrap_tls(self, client_sock: socket.socket,
                        address) -> Optional[socket.socket]:
        """Return a TLS-wrapped socket when an ssl_context is configured."""
        if self._ssl_context is None:
            return client_sock
        try:
            client_sock.settimeout(_AUTH_TIMEOUT_S)
            wrapped = self._ssl_context.wrap_socket(
                client_sock, server_side=True,
            )
            wrapped.settimeout(None)
            return wrapped
        except OSError as error:
            autocontrol_logger.info(
                "remote_desktop TLS handshake from %s failed: %r",
                address, error,
            )
            try:
                client_sock.close()
            except OSError:
                pass
            return None

    def _capture_loop(self) -> None:
        next_tick = time.monotonic()
        last_frame_hash: Optional[int] = None
        while not self._shutdown.is_set():
            try:
                frame = self._frame_provider()
            except (OSError, RuntimeError, ValueError) as error:
                autocontrol_logger.warning(
                    "remote_desktop frame capture failed: %r", error,
                )
                self._shutdown.wait(self._period)
                continue
            # Phase 2.3: drop frames that are byte-identical to the
            # previous capture. A static desktop produces the same JPEG
            # every tick (JPEG is deterministic for identical input),
            # so this skip costs nothing extra on motion-heavy
            # workloads and saves a full FPS-worth of TCP / encoder
            # bandwidth at idle.
            frame_hash = hash(frame)
            if frame_hash != last_frame_hash:
                # Phase 6.8: hand the JPEG to the configured codec.
                # JpegPassthrough yields the bytes unchanged so the
                # wire format stays identical for stock clients.
                for encoded in self._encode_for_wire(frame):
                    with self._frame_cond:
                        self._latest_frame = encoded
                        self._latest_seq += 1
                        self._frame_cond.notify_all()
                last_frame_hash = frame_hash
            next_tick += self._period
            sleep_for = max(0.0, next_tick - time.monotonic())
            if sleep_for <= 0.0:
                next_tick = time.monotonic()
            self._shutdown.wait(sleep_for)

    def _encode_for_wire(self, jpeg_bytes: bytes):
        """Wrap codec output with a 1-byte tag (skipped for JPEG)."""
        provider = self._codec_provider
        if provider.name == CODEC_JPEG:
            yield jpeg_bytes  # legacy wire format: no tag, raw JPEG
            return
        tag = bytes([codec_tag(provider.name)])
        try:
            packets = provider.encode_jpeg(jpeg_bytes)
        except (OSError, RuntimeError, ValueError) as error:
            autocontrol_logger.warning(
                "remote_desktop codec %s failed: %r", provider.name, error,
            )
            return
        for packet in packets:
            yield tag + bytes(packet)

    def _reap_dead_clients(self) -> None:
        with self._clients_lock:
            self._clients = [c for c in self._clients
                             if not c._shutdown.is_set()]

    # context manager ----------------------------------------------------

    def __enter__(self) -> "RemoteDesktopHost":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
