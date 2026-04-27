"""Detect and (opt-in) enable hardware H.264 encoding for the WebRTC host.

aiortc 1.14 hard-codes ``libx264`` as the encoder in ``H264Encoder``. To
use NVENC / QuickSync / VAAPI we monkey-patch ``av.CodecContext.create``
so any "libx264" write request gets swapped to the chosen hardware codec.
The original is kept as a fallback if the hardware open fails.

Risk: the swap is process-wide, so every libx264 encode in the process
becomes hardware-backed. For AutoControl that's the WebRTC host only —
no other component encodes H.264 — so it's safe in practice. Still,
``install_hardware_codec`` is opt-in via the GUI and logs a warning.

Diagnostic-only path: ``available_hardware_codecs()`` lists which encoders
PyAV can actually open without changing global state.
"""
from __future__ import annotations

import threading
from typing import List, Optional

try:
    import av  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Hardware codec detection requires the 'webrtc' extra (PyAV).",
    ) from exc

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_CANDIDATE_CODECS = [
    "h264_nvenc",   # NVIDIA
    "h264_qsv",     # Intel QuickSync
    "h264_amf",     # AMD
    "h264_vaapi",   # Linux VAAPI
    "h264_videotoolbox",  # macOS
]

_install_lock = threading.Lock()
_original_encode_frame = None
_active_codec: Optional[str] = None


def _can_open(codec_name: str) -> bool:
    try:
        av.CodecContext.create(codec_name, "w")
        return True
    except (av.FFmpegError, ValueError, OSError):
        return False


def available_hardware_codecs() -> List[str]:
    """Return PyAV codec names that successfully open in encode mode."""
    return [name for name in _CANDIDATE_CODECS if _can_open(name)]


def active_hardware_codec() -> Optional[str]:
    """Return the codec currently installed via :func:`install_hardware_codec`."""
    return _active_codec


def install_hardware_codec(codec_name: str) -> bool:
    """Make aiortc's H264Encoder use ``codec_name`` instead of libx264.

    Returns True if the patch is now active. Returns False if the codec
    can't be opened (no fallback installed in that case). The hardware
    encoder is created lazily on the next encode call; if the per-encoder
    open fails, that encoder falls back to libx264 silently.
    """
    global _original_encode_frame, _active_codec
    if not _can_open(codec_name):
        autocontrol_logger.warning(
            "install_hardware_codec: %s unavailable in PyAV", codec_name,
        )
        return False
    try:
        from aiortc.codecs import h264 as aiortc_h264  # type: ignore
        import fractions  # noqa: F401  used inside patched method
    except ImportError as error:
        autocontrol_logger.warning("aiortc h264 module unavailable: %r", error)
        return False
    with _install_lock:
        if _original_encode_frame is None:
            _original_encode_frame = aiortc_h264.H264Encoder._encode_frame

        target = codec_name

        def patched(self, frame, force_keyframe):
            # Replicate aiortc's reset-on-shape-change but with hw codec.
            if self.codec and (
                frame.width != self.codec.width
                or frame.height != self.codec.height
                or abs(self.target_bitrate - self.codec.bit_rate)
                / self.codec.bit_rate > 0.1
            ):
                self.buffer_data = b""
                self.buffer_pts = None
                self.codec = None
            if force_keyframe:
                frame.pict_type = av.video.frame.PictureType.I
            else:
                frame.pict_type = av.video.frame.PictureType.NONE
            if self.codec is None:
                try:
                    self.codec = av.CodecContext.create(target, "w")
                except (av.FFmpegError, ValueError, OSError) as exc:
                    autocontrol_logger.warning(
                        "hw codec %s create failed, using libx264: %r",
                        target, exc,
                    )
                    self.codec = av.CodecContext.create("libx264", "w")
                self.codec.width = frame.width
                self.codec.height = frame.height
                self.codec.bit_rate = self.target_bitrate
                self.codec.pix_fmt = "yuv420p"
                from fractions import Fraction
                self.codec.framerate = Fraction(aiortc_h264.MAX_FRAME_RATE, 1)
                self.codec.time_base = Fraction(1, aiortc_h264.MAX_FRAME_RATE)
                self.codec.options = {"level": "31", "tune": "zerolatency"}
                self.codec.profile = "Baseline"
            data_to_send = b""
            for package in self.codec.encode(frame):
                data_to_send += bytes(package)
            if data_to_send:
                yield from self._split_bitstream(data_to_send)

        aiortc_h264.H264Encoder._encode_frame = patched
        _active_codec = codec_name
    autocontrol_logger.info(
        "install_hardware_codec: aiortc libx264 -> %s", codec_name,
    )
    return True


def uninstall_hardware_codec() -> None:
    """Restore aiortc's original H264Encoder._encode_frame."""
    global _active_codec
    with _install_lock:
        if _original_encode_frame is None:
            return
        try:
            from aiortc.codecs import h264 as aiortc_h264  # type: ignore
        except ImportError:
            return
        aiortc_h264.H264Encoder._encode_frame = _original_encode_frame
        _active_codec = None
    autocontrol_logger.info("uninstall_hardware_codec: restored libx264 path")


__all__ = [
    "available_hardware_codecs",
    "active_hardware_codec",
    "install_hardware_codec",
    "uninstall_hardware_codec",
]
