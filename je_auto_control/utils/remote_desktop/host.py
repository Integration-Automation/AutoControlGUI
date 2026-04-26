"""TCP host that streams JPEG frames and applies viewer input."""
import collections
import json
import socket
import ssl
import threading
import time
from io import BytesIO
from typing import Any, Callable, Deque, List, Mapping, Optional, Sequence

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.audio import (
    AudioBackendError, AudioCapture, DEFAULT_BLOCK_FRAMES as _AUDIO_BLOCK_FRAMES,
    DEFAULT_CHANNELS as _AUDIO_CHANNELS,
    DEFAULT_SAMPLE_RATE as _AUDIO_SAMPLE_RATE,
)
from je_auto_control.utils.remote_desktop.auth import (
    NONCE_BYTES, make_nonce, verify_response,
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
from je_auto_control.utils.remote_desktop.transport import (
    MessageChannel, TcpMessageChannel,
)

FrameProvider = Callable[[], bytes]
InputDispatcher = Callable[[Mapping[str, Any]], Any]

_AUTH_TIMEOUT_S = 5.0
_DEFAULT_QUALITY = 70


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

    @property
    def address(self):
        return self._address

    def start(self) -> None:
        """Run auth, then split into sender + receiver threads."""
        try:
            self._authenticate()
        except (AuthenticationError, ProtocolError, OSError) as error:
            autocontrol_logger.info(
                "remote_desktop client %s rejected: %r", self._address, error,
            )
            self._close()
            return
        self.authenticated = True
        self._sender_thread = threading.Thread(
            target=self._send_loop, name="rd-sender", daemon=True,
        )
        self._receiver_thread = threading.Thread(
            target=self._recv_loop, name="rd-recv", daemon=True,
        )
        self._sender_thread.start()
        self._receiver_thread.start()
        if self._host._audio_enabled:
            self._audio_sender_thread = threading.Thread(
                target=self._audio_send_loop, name="rd-audio", daemon=True,
            )
            self._audio_sender_thread.start()

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
        if not verify_response(self._host._token, nonce, payload):
            self._channel.send_typed(MessageType.AUTH_FAIL, b"bad token")
            raise AuthenticationError("bad token")
        ok_payload = json.dumps(
            {"host_id": self._host.host_id}, ensure_ascii=False,
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
            except (OSError, ConnectionError) as error:
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
                except (OSError, ConnectionError) as error:
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
            except (OSError, ConnectionError, ProtocolError) as error:
                if not self._shutdown.is_set():
                    autocontrol_logger.info(
                        "remote_desktop recv from %s ended: %r",
                        self._address, error,
                    )
                self.stop()
                return
            if msg_type is MessageType.PING:
                continue
            if msg_type is MessageType.INPUT:
                self._handle_input_payload(payload)
                continue
            autocontrol_logger.info(
                "remote_desktop unexpected msg %s from %s",
                msg_type.name, self._address,
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

    def __init__(self, token: str,
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
                 enable_audio: bool = False,
                 audio_device: Optional[int] = None,
                 audio_sample_rate: int = _AUDIO_SAMPLE_RATE,
                 audio_channels: int = _AUDIO_CHANNELS,
                 audio_block_frames: int = _AUDIO_BLOCK_FRAMES,
                 audio_capture: Optional[Any] = None,
                 ) -> None:
        if not isinstance(token, str) or not token:
            raise ValueError("token must be a non-empty string")
        if fps <= 0:
            raise ValueError("fps must be positive")
        if not 1 <= int(quality) <= 95:
            raise ValueError("quality must be in [1, 95]")
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
        self._audio_enabled = bool(enable_audio)
        self._audio_device = audio_device
        self._audio_sample_rate = int(audio_sample_rate)
        self._audio_channels = int(audio_channels)
        self._audio_block_frames = int(audio_block_frames)
        self._audio_capture_override = audio_capture
        self._audio_capture: Optional[AudioCapture] = None
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
        return self._audio_enabled and self._audio_capture is not None

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
        """Bind, then launch accept + capture threads."""
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
        for thread in (self._accept_thread, self._capture_thread):
            if thread is not None:
                thread.join(timeout=timeout)
        self._accept_thread = None
        self._capture_thread = None

    def _start_audio_capture(self) -> None:
        """Open the audio input stream when ``enable_audio`` is set."""
        if not self._audio_enabled:
            return
        if self._audio_capture_override is not None:
            self._audio_capture = self._audio_capture_override
            try:
                self._audio_capture.start()
            except (AudioBackendError, OSError, RuntimeError) as error:
                autocontrol_logger.warning(
                    "remote_desktop audio capture failed to start: %r", error,
                )
                self._audio_capture = None
            return
        try:
            capture = AudioCapture(
                on_block=self._broadcast_audio,
                device=self._audio_device,
                sample_rate=self._audio_sample_rate,
                channels=self._audio_channels,
                block_frames=self._audio_block_frames,
            )
            capture.start()
        except (AudioBackendError, OSError, RuntimeError) as error:
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

    # internals -----------------------------------------------------------

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
            wrapped = self._maybe_wrap_tls(client_sock, address)
            if wrapped is None:
                continue
            try:
                channel = self._build_channel(wrapped, address)
            except (OSError, RuntimeError) as error:
                autocontrol_logger.info(
                    "remote_desktop channel handshake from %s failed: %r",
                    address, error,
                )
                try:
                    wrapped.close()
                except OSError:
                    pass
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
        except (ssl.SSLError, OSError) as error:
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
        while not self._shutdown.is_set():
            try:
                frame = self._frame_provider()
            except (OSError, RuntimeError, ValueError) as error:
                autocontrol_logger.warning(
                    "remote_desktop frame capture failed: %r", error,
                )
                self._shutdown.wait(self._period)
                continue
            with self._frame_cond:
                self._latest_frame = frame
                self._latest_seq += 1
                self._frame_cond.notify_all()
            next_tick += self._period
            sleep_for = max(0.0, next_tick - time.monotonic())
            if sleep_for == 0.0:
                next_tick = time.monotonic()
            self._shutdown.wait(sleep_for)

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
