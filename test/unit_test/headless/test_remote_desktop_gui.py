"""Qt integration tests for the Remote Desktop GUI tab.

Runs against an offscreen QApplication so it stays headless. Verifies
the viewer's FrameDisplay actually receives and decodes JPEG frames
end-to-end, and that the host preview pane mirrors what is being sent.
"""
import os
import time
from io import BytesIO

import pytest

# Force Qt to use the offscreen platform plugin so the test runs without a
# display server (and without flashing windows on a real desktop).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PIL = pytest.importorskip("PIL.Image")
pyside = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.utils.remote_desktop.registry import registry  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_registry():
    registry.disconnect_viewer()
    registry.stop_host()
    yield
    registry.disconnect_viewer()
    registry.stop_host()


def _make_jpeg(width: int = 64, height: int = 48) -> bytes:
    """Encode a small solid-color image to JPEG."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def _process_until(app: QApplication, predicate, timeout: float = 3.0,
                   interval_ms: int = 20) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(interval_ms / 1000.0)
    app.processEvents()
    return predicate()


def test_viewer_panel_renders_frame_from_host(qapp):
    from je_auto_control.gui.remote_desktop_tab import _ViewerPanel
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost

    jpeg = _make_jpeg()
    captured_input = []

    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg,
        input_dispatcher=captured_input.append,
    )
    host.start()
    registry._host = host  # noqa: SLF001  # test-only injection
    try:
        panel = _ViewerPanel()
        panel._host_field.setText("127.0.0.1")  # noqa: SLF001
        panel._port.setValue(host.port)  # noqa: SLF001
        panel._token.setText("t")  # noqa: SLF001
        panel._connect()  # noqa: SLF001
        assert _process_until(qapp, panel._display.has_image)  # noqa: SLF001
        # Display image must match the encoded frame size.
        assert panel._display._image.width() == 64  # noqa: SLF001
        assert panel._display._image.height() == 48  # noqa: SLF001
    finally:
        registry.disconnect_viewer()
        host.stop(timeout=1.0)
        registry._host = None  # noqa: SLF001


def test_host_preview_shows_streamed_frame(qapp):
    from je_auto_control.gui.remote_desktop_tab import _HostPanel
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost

    jpeg = _make_jpeg(80, 60)
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg,
    )
    host.start()
    registry._host = host  # noqa: SLF001
    try:
        panel = _HostPanel()
        # Speed the preview poll up so the test does not need to wait 250ms+.
        panel._preview_timer.setInterval(20)  # noqa: SLF001
        assert _process_until(qapp, panel._preview.has_image)  # noqa: SLF001
        assert panel._preview._image.width() == 80  # noqa: SLF001
        assert panel._preview._image.height() == 60  # noqa: SLF001
    finally:
        host.stop(timeout=1.0)
        registry._host = None  # noqa: SLF001


def test_viewer_input_round_trips_to_dispatcher(qapp):
    from je_auto_control.gui.remote_desktop_tab import _ViewerPanel
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost

    jpeg = _make_jpeg()
    captured = []
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=lambda: jpeg,
        input_dispatcher=captured.append,
    )
    host.start()
    registry._host = host  # noqa: SLF001
    try:
        panel = _ViewerPanel()
        panel._host_field.setText("127.0.0.1")  # noqa: SLF001
        panel._port.setValue(host.port)  # noqa: SLF001
        panel._token.setText("t")  # noqa: SLF001
        panel._connect()  # noqa: SLF001
        assert _process_until(qapp, panel._display.has_image)  # noqa: SLF001

        panel._send_mouse_move(11, 13)  # noqa: SLF001
        panel._send_mouse_press(11, 13, "mouse_left")  # noqa: SLF001

        assert _process_until(
            qapp,
            lambda: any(c.get("action") == "mouse_press" for c in captured),
        )
        moves = [c for c in captured if c.get("action") == "mouse_move"]
        assert any(c == {"action": "mouse_move", "x": 11, "y": 13}
                   for c in moves)
    finally:
        registry.disconnect_viewer()
        host.stop(timeout=1.0)
        registry._host = None  # noqa: SLF001
