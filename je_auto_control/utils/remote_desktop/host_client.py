"""Per-connection handler for the TCP remote-desktop host.

One instance per connected viewer, owning that viewer's auth exchange,
sender thread, audio sender thread and receiver thread, plus the routing
table that turns an inbound message type into the right handler. The
owning :class:`~je_auto_control.utils.remote_desktop.host.RemoteDesktopHost`
is referenced only through the instance passed to ``__init__``, so this
module does not import it.
"""
import collections
import json
import threading
from typing import TYPE_CHECKING, Deque, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.auth import make_nonce
from je_auto_control.utils.remote_desktop.clipboard_sync import (
    ClipboardSyncError, decode as decode_clipboard,
)
from je_auto_control.utils.remote_desktop.file_transfer import (
    FileTransferError,
)
from je_auto_control.utils.remote_desktop.host_access import (
    PERMISSION_DENIED, PERMISSION_FULL, PERMISSION_VIEW_ONLY,
    PendingViewer, _AUTH_TIMEOUT_S, _interpret_approval,
)
from je_auto_control.utils.remote_desktop.input_dispatch import (
    InputDispatchError,
)
from je_auto_control.utils.remote_desktop.protocol import (
    AuthenticationError, MessageType, ProtocolError,
)
from je_auto_control.utils.remote_desktop.transport import MessageChannel

if TYPE_CHECKING:  # avoids a runtime cycle: host imports this module
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost

_FILE_MSG_TYPES = frozenset({
    MessageType.FILE_BEGIN, MessageType.FILE_CHUNK, MessageType.FILE_END,
})


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
        # The initial cursor + frame are seeded from _send_loop (the
        # per-client sender thread), not here. start() runs on the shared
        # accept thread with the socket timeout already cleared, so sending a
        # full-screen JPEG to a viewer that authenticates then stops reading
        # would block every new accept until its send buffer drains.
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
        # Seed the viewer with the latest cursor + frame on this per-client
        # sender thread (Phase 2.3: motion-aware capture only bumps the seq on
        # change, so a viewer joining a static desktop would otherwise sit
        # blank until the host moves). Doing it here rather than in start()
        # keeps a slow-reading viewer from stalling the accept thread.
        self._host._send_initial_cursor(self)
        self._send_initial_frame()
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
        if msg_type is MessageType.USB_LIST_REQUEST:
            self._handle_usb_list_request()
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

    def _handle_usb_list_request(self) -> None:
        """Phase 6.9: enumerate the host's USB devices and ship the list back.

        Uses the existing :func:`list_usb_devices` helper so we get the
        same cross-platform behaviour as the standalone USB module.
        Errors fall back to an empty payload — the viewer should
        treat that as "host has no usable USB backend" rather than
        crashing.
        """
        try:
            from je_auto_control.utils.usb import list_usb_devices
            result = list_usb_devices()
            body = {
                "backend": result.backend,
                "devices": [d.to_dict() for d in result.devices],
            }
        except (ImportError, OSError, RuntimeError) as error:
            autocontrol_logger.info(
                "usb_list from %s failed: %r", self._address, error,
            )
            body = {"backend": "unavailable", "devices": []}
        try:
            self._channel.send_typed(
                MessageType.USB_LIST_RESPONSE,
                json.dumps(body, ensure_ascii=False).encode("utf-8"),
            )
        except OSError:
            pass

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
