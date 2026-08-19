"""Frame and cursor production for the TCP remote-desktop host.

What the host streams, as opposed to how it streams it: monitor
enumeration, mapping a monitor index to a capture region, and the default
providers that turn a screen grab into JPEG bytes and read the cursor
position. Every one of them degrades to a working fallback when the
optional dependency (``mss``, Pillow) is missing, so a stock install
still hosts.
"""
import json
import time
from io import BytesIO
from typing import (
    TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence,
)

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.protocol import MessageType
from je_auto_control.utils.remote_desktop.video_codec import (
    CODEC_JPEG, codec_tag,
)

if TYPE_CHECKING:  # avoids a runtime cycle: host_client is a sibling
    from je_auto_control.utils.remote_desktop.host_client import (
        _ClientHandler,
    )


FrameProvider = Callable[[], bytes]

CursorProvider = Callable[[], Optional[Sequence[int]]]
"""Return ``(x, y)`` in host screen coordinates, or ``None`` to skip a tick."""

_DEFAULT_QUALITY = 70

_CURSOR_POLL_INTERVAL_S = 1.0 / 30.0  # 30 Hz: smooth, low CPU on idle.

def list_host_monitors() -> List[Dict[str, Any]]:
    """Headless helper: return every monitor's geometry.

    Index 0 spans all monitors (the ``mss`` convention). Returns an
    empty list if ``mss`` is not installed, so GUI callers can show a
    disabled control instead of crashing.
    """
    from je_auto_control.utils.cv2_utils.screen_grabber import mss_grabber
    try:
        grabber = mss_grabber()
    except ImportError:
        return []
    with grabber as sct:
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
    from je_auto_control.utils.cv2_utils.screen_grabber import mss_grabber
    try:
        grabber = mss_grabber()
    except ImportError:
        autocontrol_logger.warning(
            "remote_desktop monitor_index=%d ignored: mss not installed",
            monitor_index,
        )
        return None
    with grabber as sct:
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
    """Build a JPEG frame producer using the platform's screen grabber."""
    def provide() -> bytes:
        # local import: not needed for unit tests
        from je_auto_control.utils.cv2_utils.screen_grabber import image_grabber
        grabber = image_grabber()
        if region is not None:
            x, y, width, height = (int(v) for v in region)
            bbox = (x, y, x + width, y + height)
            image = grabber.grab(bbox=bbox, all_screens=True)
        else:
            image = grabber.grab(all_screens=True)
        if image.mode != "RGB":
            image = image.convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=int(quality))
        return buffer.getvalue()
    return provide


class FrameProductionMixin:
    """Frame and cursor production half of :class:`RemoteDesktopHost`.

    The loops that turn the host screen into what viewers receive: the
    ~30 Hz cursor poll, the capture loop that paces frames at the
    configured fps, and the codec step between a JPEG frame and the bytes
    that go on the wire. Requires the host to provide ``_shutdown``,
    ``_clients``/``_clients_lock``, ``_frame_provider``,
    ``_cursor_provider``, ``_codec``, ``_fps``, ``_latest_frame`` and
    ``_frame_lock``.
    """

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
