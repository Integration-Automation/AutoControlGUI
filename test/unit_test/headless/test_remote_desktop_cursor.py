"""Headless tests for the host->viewer cursor-position broadcast."""
import threading
import time
from io import BytesIO

import pytest

from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer


def _make_jpeg() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (32, 24), color=(50, 50, 50))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


@pytest.fixture
def jpeg_bytes():
    return _make_jpeg()


def test_host_broadcasts_cursor_to_viewer(jpeg_bytes):
    """Each unique position the cursor reports reaches the viewer."""
    positions = iter([
        (10, 20), (10, 20), (15, 30), (15, 30), (200, 100),
    ])

    def cursor_provider():
        try:
            return next(positions)
        except StopIteration:
            return None

    received = []
    received_lock = threading.Lock()

    def on_cursor(x: int, y: int) -> None:
        with received_lock:
            received.append((x, y))

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        cursor_provider=cursor_provider,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
            on_cursor=on_cursor,
        )
        viewer.connect(timeout=5.0)
        try:
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                with received_lock:
                    if (10, 20) in received \
                            and (15, 30) in received \
                            and (200, 100) in received:
                        break
                time.sleep(0.05)
            with received_lock:
                snapshot = list(received)
            # Each unique position arrived; dedupe of consecutive
            # duplicates happened on the host side so the viewer never
            # sees back-to-back identical updates for a still cursor.
            assert (10, 20) in snapshot
            assert (15, 30) in snapshot
            assert (200, 100) in snapshot
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_cursor_broadcast_disabled_keeps_viewer_callback_silent(jpeg_bytes):
    """``enable_cursor_broadcast=False`` should suppress CURSOR messages."""
    received = []
    received_lock = threading.Lock()

    def on_cursor(x: int, y: int) -> None:
        with received_lock:
            received.append((x, y))

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        enable_cursor_broadcast=False,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
            on_cursor=on_cursor,
        )
        viewer.connect(timeout=5.0)
        try:
            # Give the (would-be) cursor thread plenty of poll cycles.
            time.sleep(0.5)
            with received_lock:
                assert received == []
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_cursor_provider_returning_none_is_safe(jpeg_bytes):
    """A broken cursor provider should not crash the host."""
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg_bytes,
        cursor_provider=lambda: None,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
        )
        viewer.connect(timeout=5.0)
        try:
            # Host still streams frames despite the dead cursor provider.
            time.sleep(0.3)
            assert viewer.connected
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_frame_display_paints_cursor_overlay():
    """Setting the remote cursor must mutate state + trigger update."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from je_auto_control.gui.remote_desktop.frame_display import _FrameDisplay

    display = _FrameDisplay()
    try:
        assert display._remote_cursor is None  # noqa: SLF001
        display.set_remote_cursor(40, 60)
        assert display._remote_cursor == (40, 60)  # noqa: SLF001
        display.clear_remote_cursor()
        assert display._remote_cursor is None  # noqa: SLF001
    finally:
        display.deleteLater()
