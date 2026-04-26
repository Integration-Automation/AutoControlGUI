"""Clipboard sync tests: serialization round-trip and host<->viewer flow."""
import time

import pytest

from je_auto_control.utils.remote_desktop import (
    RemoteDesktopHost, RemoteDesktopViewer,
)
from je_auto_control.utils.remote_desktop.clipboard_sync import (
    ClipboardSyncError, decode, encode_image, encode_text,
)


def _wait_until(predicate, timeout: float = 2.0,
                interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# --- serialization unit tests --------------------------------------------


def test_encode_decode_text_round_trip():
    payload = encode_text("hello 世界")
    kind, data = decode(payload)
    assert kind == "text"
    assert data == "hello 世界"


def test_encode_decode_image_round_trip():
    raw = b"\x89PNG\r\n\x1a\n_synthetic_"
    payload = encode_image(raw)
    kind, data = decode(payload)
    assert kind == "image"
    assert data == raw


def test_encode_text_rejects_non_string():
    with pytest.raises(TypeError):
        encode_text(123)  # type: ignore[arg-type]  # NOSONAR S5655  # intentional bad-type test


def test_encode_image_rejects_empty():
    with pytest.raises(ValueError):
        encode_image(b"")


def test_decode_rejects_invalid_json():
    with pytest.raises(ClipboardSyncError):
        decode(b"not json")


def test_decode_rejects_unknown_kind():
    with pytest.raises(ClipboardSyncError):
        decode(b'{"kind": "video", "data": "x"}')


def test_decode_rejects_unsupported_image_format():
    with pytest.raises(ClipboardSyncError):
        decode(b'{"kind": "image", "format": "gif", "data_b64": ""}')


def test_decode_text_missing_field():
    with pytest.raises(ClipboardSyncError):
        decode(b'{"kind": "text"}')


# --- end-to-end host<->viewer ---------------------------------------------


class _RecordingHost(RemoteDesktopHost):
    """Host that captures clipboard apply calls instead of touching the OS."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.applied = []

    def _apply_clipboard(self, kind, data) -> None:
        self.applied.append((kind, data))


def _start_host() -> _RecordingHost:
    host = _RecordingHost(
        token="tok", bind="127.0.0.1", port=0, fps=50.0,
        frame_provider=lambda: b"frame",
        input_dispatcher=lambda *_a, **_k: None,
        host_id="900800700",
    )
    host.start()
    return host


def test_viewer_send_clipboard_text_reaches_host():
    host = _start_host()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
        )
        viewer.connect(timeout=2.0)
        viewer.send_clipboard_text("ping from viewer")
        assert _wait_until(lambda: host.applied == [("text", "ping from viewer")])
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_viewer_send_clipboard_image_reaches_host():
    host = _start_host()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
        )
        viewer.connect(timeout=2.0)
        viewer.send_clipboard_image(b"\x89PNGfake")
        assert _wait_until(lambda: host.applied == [("image", b"\x89PNGfake")])
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_host_broadcast_clipboard_reaches_viewer():
    host = _start_host()
    try:
        received = []
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            on_clipboard=lambda kind, data: received.append((kind, data)),
        )
        viewer.connect(timeout=2.0)
        # Wait for the receiver thread to come up and the auth handshake
        # to count the viewer as a connected client.
        assert _wait_until(lambda: host.connected_clients == 1)
        sent = host.broadcast_clipboard_text("greetings from host")
        assert sent == 1
        assert _wait_until(
            lambda: ("text", "greetings from host") in received,
        )
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_viewer_clipboard_methods_require_connection():
    viewer = RemoteDesktopViewer(host="127.0.0.1", port=1, token="t")
    with pytest.raises(ConnectionError):
        viewer.send_clipboard_text("x")
    with pytest.raises(ConnectionError):
        viewer.send_clipboard_image(b"\x89PNGfake")


def test_host_apply_clipboard_unknown_kind_raises():
    host = _start_host()
    try:
        with pytest.raises(ValueError):
            # Bypass the recorded subclass and exercise the parent logic.
            RemoteDesktopHost._apply_clipboard(host, "video", b"")
    finally:
        host.stop(timeout=1.0)
