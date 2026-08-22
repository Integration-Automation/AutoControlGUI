"""Record incoming WebRTC video frames to an mp4 file via PyAV.

The viewer's frame callback fires on the asyncio thread. ``SessionRecorder``
is thread-safe: ``write_frame`` may be called from that thread while
``stop`` is called from the Qt thread. Only one open recording per
instance — call :meth:`stop` before reusing.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, Tuple

try:
    import av  # type: ignore
except ImportError as exc:  # pragma: no cover - 'webrtc' extra
    raise ImportError(
        "Session recording requires the 'webrtc' extra (PyAV).",
    ) from exc

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_CODEC = "libx264"
_DEFAULT_PIXEL_FORMAT = "yuv420p"

# Map container suffix → codec/pix_fmt overrides for that container.
_FORMAT_PRESETS = {
    "mp4": {"codec": "libx264", "pixel_format": "yuv420p"},
    "webm": {"codec": "libvpx-vp9", "pixel_format": "yuv420p"},
    "mkv": {"codec": "libx264", "pixel_format": "yuv420p"},
}


def preset_for_path(path) -> dict:
    """Return codec defaults for a path's extension, or empty dict."""
    suffix = str(path).rsplit(".", 1)[-1].lower()
    return _FORMAT_PRESETS.get(suffix, {})


class SessionRecorder:
    """Mux incoming ``av.VideoFrame`` instances into an mp4 file."""

    def __init__(self, output_path: str, *,
                 codec: str = _DEFAULT_CODEC,
                 pixel_format: str = _DEFAULT_PIXEL_FORMAT,
                 fps: int = 24) -> None:
        self._path = Path(output_path)
        self._codec = codec
        self._pixel_format = pixel_format
        self._fps = max(1, int(fps))
        self._lock = threading.Lock()
        self._container: Optional["av.container.OutputContainer"] = None
        self._stream: Optional["av.video.stream.VideoStream"] = None
        self._started = False
        self._closed = False

    def _open(self, frame) -> Tuple[
        "av.container.OutputContainer", "av.video.stream.VideoStream",
    ]:
        """Return the open (container, stream) pair, creating it on first use."""
        if self._container is not None and self._stream is not None:
            return self._container, self._stream
        self._path.parent.mkdir(parents=True, exist_ok=True)
        container = av.open(str(self._path), mode="w")
        stream = container.add_stream(self._codec, rate=self._fps)
        stream.width = frame.width
        stream.height = frame.height
        stream.pix_fmt = self._pixel_format
        self._container = container
        self._stream = stream
        self._started = True
        autocontrol_logger.info(
            "session_recorder: writing to %s (%dx%d @%dfps, %s)",
            self._path, frame.width, frame.height, self._fps, self._codec,
        )
        return container, stream

    def write_frame(self, frame) -> None:
        """Encode one ``av.VideoFrame``; lazy-init the container."""
        if self._closed:
            return
        with self._lock:
            if self._closed:
                return
            try:
                container, stream = self._open(frame)
                for packet in stream.encode(frame):
                    container.mux(packet)
            except (ValueError, OSError, RuntimeError) as error:
                autocontrol_logger.warning(
                    "session_recorder: write failed, stopping: %r", error,
                )
                self._closed = True
                self._teardown_locked()

    def stop(self) -> None:
        """Flush the encoder and close the file."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._teardown_locked()

    def _teardown_locked(self) -> None:
        container, stream = self._container, self._stream
        if stream is not None and container is not None:
            try:
                for packet in stream.encode(None):
                    container.mux(packet)
            except (ValueError, OSError, RuntimeError) as error:
                autocontrol_logger.debug(
                    "session_recorder: flush failed: %r", error,
                )
        if container is not None:
            try:
                container.close()
            except (ValueError, OSError, RuntimeError) as error:
                autocontrol_logger.debug(
                    "session_recorder: close failed: %r", error,
                )
        self._container = None
        self._stream = None

    @property
    def is_active(self) -> bool:
        return self._started and not self._closed

    @property
    def output_path(self) -> Path:
        return self._path


__all__ = ["SessionRecorder"]
