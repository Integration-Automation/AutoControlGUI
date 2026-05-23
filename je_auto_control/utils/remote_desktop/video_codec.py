"""Phase 6.8: pluggable video codec for the TCP / WS frame path.

The capture loop produces JPEG frames by default. That's bandwidth-cheap
for static screens (Phase 2.3 dedup makes it ~free) but expensive for
fast motion. This module adds an opt-in H.264 encoder that reuses the
PyAV machinery already pulled in by the WebRTC stack — same `[webrtc]`
extra, no new dependency.

Wire format: host and viewer agree on a codec in the ``AUTH_OK`` JSON
payload. The FRAME body becomes a 1-byte codec tag + encoded bytes:

    0x01 jpeg   — body is the raw JPEG (default; backward compatible
                  with viewers that don't read the tag)
    0x02 h264   — body is one or more H.264 NAL units (Annex-B)
    0x03 hevc   — body is HEVC NAL units (Annex-B)

Pre-existing JPEG-only viewers don't see the tag because the host
falls back to raw-JPEG mode for the legacy clients (codec
negotiation in AUTH_OK absent → assume jpeg, no tag prefix).
"""
from __future__ import annotations

from typing import Iterable, Optional

CODEC_JPEG = "jpeg"
CODEC_H264 = "h264"
CODEC_HEVC = "hevc"

_CODEC_TAGS = {
    CODEC_JPEG: 0x01,
    CODEC_H264: 0x02,
    CODEC_HEVC: 0x03,
}
_TAGS_TO_CODEC = {v: k for k, v in _CODEC_TAGS.items()}


def codec_tag(name: str) -> int:
    """Return the 1-byte wire tag for a codec name."""
    if name not in _CODEC_TAGS:
        raise ValueError(f"unknown codec: {name!r}")
    return _CODEC_TAGS[name]


def codec_from_tag(tag: int) -> str:
    """Return the codec name for a wire tag byte."""
    if tag not in _TAGS_TO_CODEC:
        raise ValueError(f"unknown codec tag: 0x{tag:02x}")
    return _TAGS_TO_CODEC[tag]


class CodecProvider:
    """Abstract: convert raw frames into wire-ready encoded packets.

    The host's capture loop calls :meth:`encode_jpeg` for every JPEG
    that came out of the frame provider. ``yield`` zero or more
    packets — typically one per input frame for I-frame codecs, but
    P-frame codecs may emit nothing if the encoder is still buffering.
    """

    name: str = "raw"

    def encode_jpeg(self, jpeg_bytes: bytes) -> Iterable[bytes]:
        """Yield wire-ready packets for one captured JPEG."""
        raise NotImplementedError

    def close(self) -> None:
        """Release encoder resources. Idempotent."""


class JpegPassthrough(CodecProvider):
    """Default codec: emit the JPEG verbatim, one packet per frame."""

    name = CODEC_JPEG

    def encode_jpeg(self, jpeg_bytes: bytes) -> Iterable[bytes]:
        return [jpeg_bytes] if jpeg_bytes else []


class H264CodecProvider(CodecProvider):
    """libx264 encoder via PyAV. Imports ``av`` lazily.

    Raises :class:`ImportError` from the constructor when PyAV is not
    installed. Operators trigger this provider by passing
    ``codec_provider=H264CodecProvider(...)`` to :class:`RemoteDesktopHost`;
    the legacy default (JPEG) keeps working without the extras.
    """

    name = CODEC_H264

    def __init__(self,
                 *, fps: int = 30, bitrate: int = 4_000_000,
                 width: Optional[int] = None,
                 height: Optional[int] = None,
                 gop_size: int = 60) -> None:
        try:
            import av  # noqa: F401  imported for the import check
        except ImportError as exc:  # pragma: no cover - optional dep
            raise ImportError(
                "H.264 codec requires the 'webrtc' extra: "
                "pip install je_auto_control[webrtc]",
            ) from exc
        self._fps = int(fps)
        self._bitrate = int(bitrate)
        self._width = width
        self._height = height
        self._gop_size = int(gop_size)
        self._container = None
        self._stream = None
        self._closed = False

    def _ensure_stream(self, width: int, height: int) -> None:
        if self._stream is not None:
            return
        import av
        import io
        self._buffer = io.BytesIO()
        # ``annexb`` ensures NAL units are emitted with the standard
        # ``00 00 00 01`` start codes so a viewer can hand the bytes
        # straight to a hardware decoder.
        self._container = av.open(self._buffer, mode="w", format="h264")
        stream = self._container.add_stream("h264", rate=self._fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.bit_rate = self._bitrate
        stream.options = {
            "preset": "veryfast",
            "tune": "zerolatency",
            "g": str(self._gop_size),
        }
        self._stream = stream

    def encode_jpeg(self, jpeg_bytes: bytes) -> Iterable[bytes]:
        if self._closed or not jpeg_bytes:
            return ()
        import av  # noqa: F401  lazy keep
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(jpeg_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        self._ensure_stream(img.width, img.height)
        frame = av.VideoFrame.from_image(img)
        frame.pts = None
        packets = []
        for packet in self._stream.encode(frame):
            packets.append(bytes(packet))
        return packets

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._stream is not None:
            try:
                # Drain remaining buffered packets — PyAV requires iterating
                # ``encode(None)`` to flush trailing frames before close.
                for _packet in self._stream.encode(None):
                    del _packet
            except (ValueError, RuntimeError):
                pass
        if self._container is not None:
            try:
                self._container.close()
            except (ValueError, RuntimeError):
                pass


def is_h264_available() -> bool:
    """Return True iff PyAV is importable in the current process."""
    try:
        import av  # noqa: F401
    except ImportError:
        return False
    return True


__all__ = [
    "CODEC_JPEG", "CODEC_H264", "CODEC_HEVC",
    "CodecProvider", "JpegPassthrough", "H264CodecProvider",
    "codec_tag", "codec_from_tag", "is_h264_available",
]
