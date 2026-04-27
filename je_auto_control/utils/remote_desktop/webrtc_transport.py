"""Shared WebRTC plumbing: asyncio bridge thread, screen video track, config.

aiortc is asyncio-native but the rest of AutoControl is thread-based, so the
bridge owns one background event loop and exposes a sync ``submit()`` that
returns ``concurrent.futures.Future``. Importing this module does NOT start
the loop; callers do that explicitly via :func:`get_bridge`.
"""
from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

try:
    import av  # type: ignore
    import numpy as np
    from aiortc import (
        RTCConfiguration, RTCIceServer, RTCPeerConnection,
        RTCSessionDescription, VideoStreamTrack,
    )
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError(
        "WebRTC transport requires the 'webrtc' extra: "
        "pip install je_auto_control[webrtc]"
    ) from exc

try:
    import mss  # type: ignore
except ImportError as exc:  # pragma: no cover - mss is a base dep
    raise ImportError("mss is required for screen capture") from exc


_DEFAULT_STUN = "stun:stun.l.google.com:19302"
_DEFAULT_STUN_SERVERS = (
    "stun:stun.l.google.com:19302",
    "stun:stun1.l.google.com:19302",
    "stun:stun.cloudflare.com:3478",
    "stun:stun.nextcloud.com:443",
    "stun:openrelay.metered.ca:80",
)
_ICE_GATHER_TIMEOUT_S = 8.0


# Maps bandwidth preset names to (fps, jpeg-equivalent quality hint).
# aiortc's default video bitrate is set by the negotiated codec; the fps
# clamp is the most reliable cross-codec lever we have without dropping
# into encoder-specific options. "Auto" returns (24, "auto") and the
# caller should treat it as "use defaults / pick from observed RTT".
BANDWIDTH_PRESETS = {
    "auto": {"fps": 24, "label": "Auto"},
    "low": {"fps": 10, "label": "Low (cellular)"},
    "mid": {"fps": 18, "label": "Medium"},
    "high": {"fps": 30, "label": "High (LAN)"},
}


def fps_for_preset(name: str) -> int:
    return int(BANDWIDTH_PRESETS.get(name.lower(), BANDWIDTH_PRESETS["auto"])["fps"])


@dataclass
class WebRTCConfig:
    """User-facing config for both host and viewer."""
    ice_servers: List[str] = field(
        default_factory=lambda: list(_DEFAULT_STUN_SERVERS),
    )
    turn_url: Optional[str] = None
    turn_username: Optional[str] = None
    turn_credential: Optional[str] = None
    monitor_index: int = 1  # mss numbers start at 1; 0 = "all monitors"
    fps: int = 24
    region: Optional[Sequence[int]] = None  # (x, y, w, h) overrides monitor
    show_cursor: bool = True  # overlay cursor position on captured frames
    # Bidirectional screen share: host requests viewer video; viewer offers it.
    accept_viewer_video: bool = False
    share_my_screen: bool = False
    # Opus mic uplink: host advertises recvonly audio; viewer attaches OpusMicAudioTrack.
    accept_viewer_audio_opus: bool = False
    share_my_audio_opus: bool = False
    # Hard upload bitrate cap (kbps); 0 = no cap. Applied via aiortc encoder.
    max_bitrate_kbps: int = 0
    # Host → viewer voice (host's mic streams to all viewers).
    host_voice: bool = False

    def to_rtc_configuration(self) -> RTCConfiguration:
        servers: List[RTCIceServer] = [
            RTCIceServer(urls=url) for url in self.ice_servers
        ]
        if self.turn_url:
            servers.append(RTCIceServer(
                urls=self.turn_url,
                username=self.turn_username,
                credential=self.turn_credential,
            ))
        return RTCConfiguration(iceServers=servers)


class _AsyncioBridge:
    """Background event loop shared by host and viewer instances."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._loop is not None:
                return
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run, name="webrtc-loop", daemon=True,
            )
            self._thread.start()
            autocontrol_logger.info("webrtc bridge: event loop started")

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(self, coro) -> Future:
        """Schedule a coroutine; returns ``concurrent.futures.Future``."""
        self.start()
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def call_soon(self, callback, *args) -> None:
        """Schedule a sync callable from any thread."""
        self.start()
        self._loop.call_soon_threadsafe(callback, *args)

    def stop(self) -> None:
        with self._lock:
            if self._loop is None:
                return
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=2.0)
            self._loop.close()
            self._loop = None
            self._thread = None


_bridge = _AsyncioBridge()


def get_bridge() -> _AsyncioBridge:
    """Return the shared asyncio bridge (lazily started)."""
    return _bridge


# --- screen video track -------------------------------------------------------

_capture_local = threading.local()


def _get_cursor_position() -> Optional[tuple]:
    """Return absolute (x, y) cursor position, or None on unsupported platforms."""
    import sys as _sys
    try:
        if _sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            point = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                return point.x, point.y
            return None
        if _sys.platform == "darwin":
            from Quartz import CGEventSourceGetMouseState  # type: ignore
            location = CGEventSourceGetMouseState(0)
            return int(location.x), int(location.y)
        try:
            from Xlib import display as _xdisplay  # type: ignore
            data = _xdisplay.Display().screen().root.query_pointer()._data
            return data["root_x"], data["root_y"]
        except ImportError:
            return None
    except (OSError, RuntimeError):
        return None


def _draw_cursor_overlay(arr_bgr: "np.ndarray", x: int, y: int) -> None:
    """Draw a small ring at (x, y) in BGR, in-place. No-op if out of bounds."""
    height, width = arr_bgr.shape[:2]
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    radius = 8
    inner = 2
    yellow = np.array([0, 255, 255], dtype=np.uint8)
    black = np.array([0, 0, 0], dtype=np.uint8)
    yy, xx = np.ogrid[max(0, y - radius - 1):min(height, y + radius + 2),
                      max(0, x - radius - 1):min(width, x + radius + 2)]
    dist_sq = (xx - x) ** 2 + (yy - y) ** 2
    ring = (dist_sq >= (radius - 1) ** 2) & (dist_sq <= radius ** 2)
    core = dist_sq <= inner ** 2
    region = arr_bgr[max(0, y - radius - 1):min(height, y + radius + 2),
                     max(0, x - radius - 1):min(width, x + radius + 2)]
    region[ring] = yellow
    region[core] = black


def _resolve_monitor(sct: "mss.base.MSSBase", index: int) -> dict:
    monitors = sct.monitors
    if not monitors:
        raise RuntimeError("mss reported no monitors")
    if index < 0 or index >= len(monitors):
        index = 1 if len(monitors) > 1 else 0
    return monitors[index]


def _capture_frame(monitor: dict) -> "np.ndarray":
    sct = getattr(_capture_local, "sct", None)
    if sct is None:
        sct = mss.mss()
        _capture_local.sct = sct
    img = sct.grab(monitor)
    arr = np.frombuffer(img.bgra, dtype=np.uint8).reshape(
        img.height, img.width, 4,
    )
    return np.ascontiguousarray(arr[:, :, :3])


class ScreenVideoTrack(VideoStreamTrack):
    """``VideoStreamTrack`` that pumps screen captures at a target FPS."""

    kind = "video"

    def __init__(self, monitor_index: int = 1, fps: int = 24,
                 region: Optional[Sequence[int]] = None,
                 show_cursor: bool = True) -> None:
        super().__init__()
        self._monitor_index = monitor_index
        self._fps = max(1, min(60, int(fps)))
        self._period = 1.0 / self._fps
        self._region = region
        self._show_cursor = show_cursor
        self._monitor: Optional[dict] = None
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="rd-capture",
        )
        self._last_emit: Optional[float] = None

    @property
    def fps(self) -> int:
        return self._fps

    def set_target_fps(self, fps: int) -> None:
        """Tune capture rate at runtime; clamped to 1..60. Used by the
        adaptive-bitrate controller — fps is aiortc's only reliable lever
        for live bandwidth control without restarting the encoder.
        """
        new_fps = max(1, min(60, int(fps)))
        if new_fps == self._fps:
            return
        self._fps = new_fps
        self._period = 1.0 / new_fps

    def set_target_monitor(self, index: int) -> None:
        """Switch which monitor we capture, mid-stream.

        Forces ``_resolve()`` to re-look-up the monitor on next ``recv``.
        Resolution change triggers aiortc to renegotiate the encoder
        automatically.
        """
        self._monitor_index = int(index)
        self._monitor = None  # invalidate cache

    def _resolve(self) -> dict:
        if self._monitor is not None:
            return self._monitor
        if self._region is not None:
            x, y, width, height = (int(v) for v in self._region)
            self._monitor = {"left": x, "top": y,
                             "width": width, "height": height}
        else:
            sct = getattr(_capture_local, "sct", None)
            if sct is None:
                sct = mss.mss()
                _capture_local.sct = sct
            self._monitor = _resolve_monitor(sct, self._monitor_index)
        return self._monitor

    async def recv(self):
        if self._last_emit is None:
            self._last_emit = time.monotonic()
        else:
            elapsed = time.monotonic() - self._last_emit
            sleep_for = self._period - elapsed
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            self._last_emit = time.monotonic()
        pts, time_base = await self.next_timestamp()
        loop = asyncio.get_event_loop()
        monitor = self._resolve()
        frame_array = await loop.run_in_executor(
            self._executor, _capture_frame, monitor,
        )
        if self._show_cursor:
            cursor = _get_cursor_position()
            if cursor is not None:
                local_x = cursor[0] - monitor.get("left", 0)
                local_y = cursor[1] - monitor.get("top", 0)
                _draw_cursor_overlay(frame_array, local_x, local_y)
        video_frame = av.VideoFrame.from_ndarray(frame_array, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    def stop(self) -> None:
        try:
            super().stop()
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)


# --- ICE gathering helper -----------------------------------------------------

async def wait_for_ice_gathering(pc: RTCPeerConnection,
                                 timeout: float = _ICE_GATHER_TIMEOUT_S) -> None:
    """Block until the PeerConnection has gathered all local ICE candidates."""
    if pc.iceGatheringState == "complete":
        return
    future: asyncio.Future = asyncio.get_event_loop().create_future()

    @pc.on("icegatheringstatechange")
    def _on_change() -> None:
        if pc.iceGatheringState == "complete" and not future.done():
            future.set_result(None)

    try:
        # asyncio.timeout() context manager only landed in Python 3.11;
        # this project supports 3.10, where wait_for(timeout=...) is the
        # idiomatic primitive.
        await asyncio.wait_for(future, timeout=timeout)  # NOSONAR — Python 3.10 compatibility (asyncio.timeout requires 3.11+)
    except asyncio.TimeoutError:
        autocontrol_logger.warning(
            "webrtc: ICE gather timeout; sending what we have",
        )


__all__ = [
    "WebRTCConfig",
    "ScreenVideoTrack",
    "RTCConfiguration",
    "RTCIceServer",
    "RTCPeerConnection",
    "RTCSessionDescription",
    "get_bridge",
    "wait_for_ice_gathering",
]
