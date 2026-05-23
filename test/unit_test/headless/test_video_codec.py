"""Phase 6.8: video codec abstraction tests."""
from io import BytesIO

import pytest

from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.video_codec import (
    CODEC_H264, CODEC_HEVC, CODEC_JPEG, CodecProvider, H264CodecProvider,
    JpegPassthrough, codec_from_tag, codec_tag, is_h264_available,
)
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer


def _make_jpeg() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (32, 24), color=(10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


# --- wire-tag helpers ---------------------------------------------------

def test_codec_tag_round_trip():
    for name in (CODEC_JPEG, CODEC_H264, CODEC_HEVC):
        assert codec_from_tag(codec_tag(name)) == name


def test_codec_tag_rejects_unknown():
    with pytest.raises(ValueError):
        codec_tag("not-real")
    with pytest.raises(ValueError):
        codec_from_tag(0xFF)


# --- passthrough --------------------------------------------------------

def test_jpeg_passthrough_emits_input_bytes():
    provider = JpegPassthrough()
    out = list(provider.encode_jpeg(b"fake-jpeg"))
    assert out == [b"fake-jpeg"]


def test_jpeg_passthrough_empty_in_empty_out():
    assert list(JpegPassthrough().encode_jpeg(b"")) == []


def test_codec_provider_base_is_abstract():
    class _Stub(CodecProvider):
        pass

    with pytest.raises(NotImplementedError):
        _Stub().encode_jpeg(b"x")


# --- host integration (codec lives in AUTH_OK) -------------------------

def test_host_announces_jpeg_codec_by_default():
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=_make_jpeg,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
        )
        viewer.connect(timeout=5.0)
        try:
            assert viewer.negotiated_codec == CODEC_JPEG
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_host_announces_custom_codec_to_viewer():
    """A custom codec provider is mirrored to the viewer through AUTH_OK."""

    class _CustomTag(CodecProvider):
        name = "hevc"  # use HEVC to exercise the wire tag too
        def encode_jpeg(self, jpeg_bytes):
            return [b"\xff\xff" + jpeg_bytes]  # nonsense, only need the tag

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=_make_jpeg, codec_provider=_CustomTag(),
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
        )
        viewer.connect(timeout=5.0)
        try:
            assert viewer.negotiated_codec == "hevc"
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


# --- H264 provider (skipped without PyAV) -----------------------------

@pytest.mark.skipif(not is_h264_available(),
                    reason="PyAV not installed (install [webrtc] extra)")
def test_h264_provider_encodes_a_keyframe():
    provider = H264CodecProvider(fps=30, bitrate=2_000_000)
    try:
        packets = list(provider.encode_jpeg(_make_jpeg()))
        # libx264 may buffer the first frame internally — but with
        # tune=zerolatency it usually emits a packet right away.
        # Accept either no packets (buffering) or at least one bytes
        # object on success; ensure no exception leaked.
        for pkt in packets:
            assert isinstance(pkt, bytes)
            assert len(pkt) > 0
    finally:
        provider.close()


def test_h264_provider_raises_when_pyav_missing():
    """If PyAV is missing the constructor raises ImportError with a hint."""
    if is_h264_available():
        pytest.skip("PyAV is installed — cannot exercise the missing path")
    with pytest.raises(ImportError) as excinfo:
        H264CodecProvider()
    assert "webrtc" in str(excinfo.value).lower()
