"""TCP host that streams JPEG frames and applies viewer input."""
import json
import socket
import ssl
import threading
import time
from typing import Any, Callable, List, Mapping, Optional, Sequence

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.audio import (
    AudioCapture, AudioCaptureConfig,
)
from je_auto_control.utils.remote_desktop.auth import (
    verify_response,
)
from je_auto_control.utils.remote_desktop.clipboard_sync import (
    encode_image, encode_text,
)
from je_auto_control.utils.remote_desktop.file_transfer import (
    FileReceiver, FileTransferError, send_file,
)
from je_auto_control.utils.remote_desktop.host_id import (
    load_or_create_host_id, validate_host_id,
)
from je_auto_control.utils.remote_desktop.input_dispatch import (
    dispatch_input,
)
from je_auto_control.utils.remote_desktop.protocol import (
    MessageType,
)
from je_auto_control.utils.remote_desktop.resume_tokens import (
    ResumeTokenStore,
)
from je_auto_control.utils.remote_desktop.video_codec import (
    CodecProvider, JpegPassthrough,
)
from je_auto_control.utils.remote_desktop.transport import (
    MessageChannel, TcpMessageChannel,
)
from je_auto_control.utils.remote_desktop.host_access import (
    PendingViewerCallback, _AUTH_TIMEOUT_S, _candidate_totp_codes,
    _compile_ip_allowlist, _ip_in_allowlist,
)
from je_auto_control.utils.remote_desktop.host_capture import (
    CursorProvider, FrameProductionMixin, FrameProvider,
    _DEFAULT_QUALITY, _default_frame_provider,
    _resolve_cursor_provider, _resolve_monitor_region,
)
from je_auto_control.utils.remote_desktop.host_client import (
    _ClientHandler,
)

InputDispatcher = Callable[[Mapping[str, Any]], Any]
# accept() 的輪詢間隔，用來定期檢查 _shutdown 旗標。
# How long accept() blocks before re-checking the _shutdown flag.
_ACCEPT_POLL_TIMEOUT_S = 0.5
_FILE_MSG_TYPES = frozenset({
    MessageType.FILE_BEGIN, MessageType.FILE_CHUNK, MessageType.FILE_END,
})


def _validate_host_args(token: str, fps: float, quality: int) -> None:
    """Throw early on bad constructor args so the host never starts broken."""
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    if fps <= 0:
        raise ValueError("fps must be positive")
    if not 1 <= quality <= 95:
        raise ValueError("quality must be in [1, 95]")


class RemoteDesktopHost(FrameProductionMixin):
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
        # 保護 start()/stop() 互斥。類別文件承諾「start() 具冪等性、
        # stop() 可從任何執行緒呼叫」，但兩者原本毫無互斥，交錯時
        # stop() 會在 start() 指派與啟動執行緒之間把欄位清成 None。
        # Serialises start() against stop(). The class contract promises
        # "start() is idempotent and stop() can be called from any thread",
        # but nothing enforced it: an interleaved stop() nulls _capture_thread
        # between start()'s assignment and its .start() call. This is the
        # outermost lock — always taken before _clients_lock, never after.
        self._lifecycle_lock = threading.RLock()
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
        with self._lifecycle_lock:
            self._start_locked()

    def _start_locked(self) -> None:
        if self.is_running:
            return
        self._shutdown.clear()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._bind, self._requested_port))
        sock.listen(self._max_clients)
        # Configure on the owning thread, before publishing the socket: leaving
        # this to the accept thread races a concurrent stop() closing it, which
        # makes settimeout raise WSAENOTSOCK outside any handler.
        sock.settimeout(_ACCEPT_POLL_TIMEOUT_S)
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
        with self._lifecycle_lock:
            self._stop_locked(timeout)

    def _stop_locked(self, timeout: float) -> None:
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
            # is_alive() also guards the not-yet-started case: start() assigns
            # these attributes before calling start() on them, and stop()'s
            # guard (_listen_sock) is already set by then, so a concurrent
            # stop() can reach a Thread that was never started. join() on one
            # raises RuntimeError and aborts the rest of teardown.
            if thread is not None and thread.is_alive():
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
        # The timeout is set by start() on the owning thread, before the socket
        # is published: calling settimeout() here would race a concurrent
        # stop() closing it and raise WSAENOTSOCK outside any handler.
        listen = self._listen_sock
        if listen is None:
            return
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
            # Prune handlers whose viewer already disconnected *before* the
            # capacity check below. Otherwise a client table filled with
            # max_clients dead handlers rejects every new connection forever:
            # the reject branch continues without ever reaping (the reap used
            # to run only on the accept-success path).
            self._reap_dead_clients()
            with self._clients_lock:
                # Re-check under the lock. _open_channel above performs the
                # auth/TLS handshake, which can take up to _AUTH_TIMEOUT_S; a
                # stop() during that window sets _shutdown and then snapshots
                # and clears _clients under this same lock. Without this check
                # the handler is registered *after* that snapshot, so nothing
                # ever stops it — leaving a viewer dispatching input to a host
                # the operator has already stopped.
                if self._shutdown.is_set():
                    autocontrol_logger.info(
                        "remote_desktop dropping %s: host stopped during "
                        "handshake", address,
                    )
                    handler._close()
                    return
                if len(self._clients) >= self._max_clients:
                    autocontrol_logger.info(
                        "remote_desktop dropping %s: max_clients reached",
                        address,
                    )
                    handler._close()
                    continue
                self._clients.append(handler)
            handler.start()

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
