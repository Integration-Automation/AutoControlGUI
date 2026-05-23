"""Phase 5.1 + 5.2: chat broadcast and multi-viewer cursor relay tests."""
import threading
import time
from io import BytesIO

import pytest

from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer


def _make_jpeg() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (16, 16), color=(0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


@pytest.fixture
def jpeg_bytes():
    return _make_jpeg()


# --- Phase 5.2: chat ----------------------------------------------------

def test_host_broadcasts_chat_to_viewer(jpeg_bytes):
    received = []
    lock = threading.Lock()

    def on_chat(sender: str, text: str) -> None:
        with lock:
            received.append((sender, text))

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
            on_chat=on_chat,
        )
        viewer.connect(timeout=5.0)
        try:
            sent = host.broadcast_chat("hello viewer")
            assert sent == 1
            deadline = time.monotonic() + 2.0
            while not received and time.monotonic() < deadline:
                time.sleep(0.05)
            with lock:
                assert ("host", "hello viewer") in received
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_viewer_can_chat_back_to_host(jpeg_bytes):
    received = []
    lock = threading.Lock()

    def host_on_chat(sender: str, text: str) -> None:
        with lock:
            received.append((sender, text))

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        on_chat=host_on_chat,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(host="127.0.0.1", port=host.port, token="t")
        viewer.connect(timeout=5.0)
        try:
            viewer.send_chat("ping from viewer", sender="alice")
            deadline = time.monotonic() + 2.0
            while not received and time.monotonic() < deadline:
                time.sleep(0.05)
            with lock:
                assert ("alice", "ping from viewer") in received
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_broadcast_chat_with_empty_text_is_noop(jpeg_bytes):
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
    )
    host.start()
    try:
        assert host.broadcast_chat("") == 0
        assert host.broadcast_chat(None) == 0  # type: ignore[arg-type]
    finally:
        host.stop(timeout=1.0)


# --- Phase 5.1: multi-viewer cursor relay -------------------------------

def test_viewer_cursor_payload_routes_to_separate_callback(jpeg_bytes):
    """A CURSOR message with viewer_id fires on_viewer_cursor, not on_cursor."""
    main_cursor = []
    viewer_cursors = []
    lock = threading.Lock()

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        # Disable host cursor broadcast so we only see what we explicitly send.
        enable_cursor_broadcast=False,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
            on_cursor=lambda x, y: main_cursor.append((x, y)),
            on_viewer_cursor=lambda vid, x, y:
                viewer_cursors.append((vid, x, y)),
        )
        viewer.connect(timeout=5.0)
        try:
            # Simulate MultiViewerHost relaying another operator's cursor.
            host.broadcast_viewer_cursor("alice", 200, 300)
            deadline = time.monotonic() + 2.0
            while not viewer_cursors and time.monotonic() < deadline:
                time.sleep(0.05)
            with lock:
                assert ("alice", 200, 300) in viewer_cursors
                # The main on_cursor callback must NOT have fired — that
                # one is reserved for the host's own pointer.
                assert main_cursor == []
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)
