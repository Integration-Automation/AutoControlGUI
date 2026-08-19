"""The capture layer must reach the platform backend, not Pillow directly.

Every locator, OCR call, screenshot, recording and remote-desktop frame in
the framework used to call ``PIL.ImageGrab`` or ``mss`` itself. Both read the
X11 root window on Linux, which under Wayland belongs to XWayland and holds
none of the native Wayland windows — so all of them captured a blank screen
while the Wayland backend's own capture sat unused and unreachable.

These tests pin the seam that fixes it: when the active backend publishes
``grab_image`` every capture path goes through it, and when it does not
(Windows, macOS, X11) the real libraries are handed back untouched. No Qt,
and no dependency on the host's display server.
"""
import contextlib
import sys
from unittest.mock import patch

import pytest
from PIL import Image

from je_auto_control.utils.cv2_utils import screen_grabber


class _FakeBackendScreen:
    """Minimal stand-in for a backend screen module that can capture."""

    def __init__(self, size=(8, 4), colour=(10, 20, 30), origin=(0, 0)):
        self._size = size
        self._colour = colour
        self._origin = origin
        self.calls = []

    def grab_image(self, screen_region=None):
        self.calls.append(screen_region)
        if screen_region is None:
            return Image.new("RGB", self._size, self._colour)
        x1, y1, x2, y2 = screen_region
        return Image.new("RGB", (x2 - x1, y2 - y1), self._colour)

    def size(self):
        return self._size

    def layout_origin(self):
        return self._origin


@contextlib.contextmanager
def _with_backend(backend):
    """Patch the wrapper's ``screen`` so the grabbers see our fake backend.

    Both halves of the seam have to come from the fake. ``mss_grabber``
    reports its layout from ``platform_wrapper.screen.size()``, so patching
    only ``grab_image`` would leave ``monitors`` describing whatever display
    the test host happens to have -- passing on a 1920x1080 desktop and
    failing under a 1280x800 Xvfb for reasons unrelated to the code here.
    """
    with patch.object(screen_grabber, "backend_grab_image",
                      return_value=backend.grab_image):
        with patch.object(screen_grabber, "_backend_screen_size",
                          side_effect=backend.size):
            with patch.object(screen_grabber, "backend_layout_origin",
                              side_effect=backend.layout_origin):
                yield


# === Backend detection =====================================================

def test_backend_grab_image_is_none_without_a_publishing_backend():
    """Windows / macOS / X11 publish no grab_image, and must keep using the
    real libraries — this fix must change nothing on those platforms."""
    class _PlainScreen:
        def size(self):
            return (1920, 1080)

    stub = type(sys)("stub")
    stub.screen = _PlainScreen()
    with patch.dict(sys.modules,
                    {"je_auto_control.wrapper.platform_wrapper": stub}):
        assert screen_grabber.backend_grab_image() is None


def test_image_grabber_returns_pillow_when_no_backend_publishes_capture():
    with patch.object(screen_grabber, "backend_grab_image",
                      return_value=None):
        from PIL import ImageGrab
        assert screen_grabber.image_grabber() is ImageGrab


# === ImageGrab-shaped adapter ==============================================

def test_image_grabber_routes_full_screen_grab_to_the_backend():
    backend = _FakeBackendScreen()
    with _with_backend(backend):
        image = screen_grabber.image_grabber().grab()
    assert backend.calls == [None]
    assert image.size == (8, 4)


def test_image_grabber_passes_the_bbox_through_as_a_region():
    backend = _FakeBackendScreen()
    with _with_backend(backend):
        image = screen_grabber.image_grabber().grab(bbox=(2, 3, 6, 9))
    assert backend.calls == [[2, 3, 6, 9]]
    assert image.size == (4, 6)


def test_image_grabber_tolerates_pillow_only_keywords():
    """Callers pass all_screens / xdisplay; a Wayland capture already spans
    the whole layout, so these must be accepted and ignored rather than
    raising TypeError deep inside a locator."""
    backend = _FakeBackendScreen()
    with _with_backend(backend):
        grabber = screen_grabber.image_grabber()
        grabber.grab(all_screens=True)
        grabber.grab(bbox=(0, 0, 2, 2), all_screens=True, xdisplay=None)
    assert backend.calls == [None, [0, 0, 2, 2]]


def test_logical_frame_capture_goes_through_the_backend():
    """grab_logical feeds the template, OCR and visual-match locators; it
    resolves its grabber lazily, so the seam has to hold there too."""
    from je_auto_control.utils.monitor_layout import logical_frame
    backend = _FakeBackendScreen()
    # Pin the virtual-desktop metrics so the assertion is about the grabber
    # seam, not about whatever monitors this test host happens to have.
    flat_desktop = {76: 0, 77: 0, 78: 8, 79: 4}
    with _with_backend(backend):
        image, origin_x, origin_y = logical_frame.grab_logical(
            metrics=flat_desktop.__getitem__)
    assert (origin_x, origin_y) == (0, 0)
    assert image.size == (8, 4)
    assert backend.calls == [None]


def test_pil_screenshot_goes_through_the_backend(tmp_path):
    from je_auto_control.utils.cv2_utils import screenshot as screenshot_module
    backend = _FakeBackendScreen()
    target = tmp_path / "shot.png"
    with _with_backend(backend):
        image = screenshot_module.pil_screenshot(file_path=str(target))
    assert image.size == (8, 4)
    assert target.exists()
    assert backend.calls == [None]


# === mss-shaped adapter ====================================================

def test_mss_grabber_reports_the_layout_as_monitor_zero_and_one():
    backend = _FakeBackendScreen(size=(1920, 1080))
    with _with_backend(backend):
        with screen_grabber.mss_grabber() as sct:
            monitors = sct.monitors
    assert len(monitors) == 2
    assert monitors[0] == {"left": 0, "top": 0,
                           "width": 1920, "height": 1080}
    # Callers that default to "the first real screen" must still get a frame.
    assert monitors[1] == monitors[0]


def test_mss_grabber_reports_a_negative_layout_origin():
    """Regression: ``monitors`` was hardcoded to start at (0, 0).

    A Wayland layout starts at a negative coordinate whenever an output
    sits left of or above the origin, and mss's own callers already expect
    a negative ``left`` there. ``grab`` feeds the rectangle straight back as
    a capture region, so claiming (0, 0) grabbed half of one monitor plus
    the empty space past the desktop's right edge.
    """
    backend = _FakeBackendScreen(size=(2560, 720), origin=(-1280, 0))
    with _with_backend(backend):
        with screen_grabber.mss_grabber() as sct:
            monitors = sct.monitors
            sct.grab(monitors[1])
    assert monitors[0] == {"left": -1280, "top": 0,
                           "width": 2560, "height": 720}
    assert backend.calls == [[-1280, 0, 1280, 720]]


def test_backend_layout_origin_is_the_origin_without_a_publishing_backend():
    """Windows / macOS / X11 publish no layout_origin, and a guess would be worse."""
    class _PlainScreen:
        def size(self):
            return (1920, 1080)

    stub = type(sys)("stub")
    stub.screen = _PlainScreen()
    with patch.dict(sys.modules,
                    {"je_auto_control.wrapper.platform_wrapper": stub}):
        assert screen_grabber.backend_layout_origin() == (0, 0)


def test_backend_layout_origin_reads_a_publishing_backend():
    backend = _FakeBackendScreen(size=(2560, 720), origin=(-1280, -200))
    stub = type(sys)("stub")
    stub.screen = backend
    with patch.dict(sys.modules,
                    {"je_auto_control.wrapper.platform_wrapper": stub}):
        assert screen_grabber.backend_layout_origin() == (-1280, -200)


def test_mss_shot_exposes_the_bgra_buffer_callers_read():
    """mss consumers read .bgra / .size directly (the MCP monitor grab) and
    hand the shot to numpy (the recorder), so both shapes must hold."""
    backend = _FakeBackendScreen(size=(2, 1), colour=(10, 20, 30))
    with _with_backend(backend):
        with screen_grabber.mss_grabber() as sct:
            shot = sct.grab({"left": 0, "top": 0, "width": 2, "height": 1})
    assert shot.size == (2, 1)
    assert (shot.width, shot.height) == (2, 1)
    # BGRA order, so the blue channel comes first.
    assert shot.bgra[:4] == bytes((30, 20, 10, 255))
    assert shot.rgb[:3] == bytes((10, 20, 30))
    rebuilt = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    assert rebuilt.getpixel((0, 0)) == (10, 20, 30)


def test_mss_shot_converts_to_a_numpy_bgra_array():
    numpy = pytest.importorskip("numpy")
    backend = _FakeBackendScreen(size=(3, 2))
    with _with_backend(backend):
        with screen_grabber.mss_grabber() as sct:
            shot = sct.grab({"left": 0, "top": 0, "width": 3, "height": 2})
    array = numpy.array(shot)
    assert array.shape == (2, 3, 4)


# === Whole chain, public API down to the compositor's tool =================

def _solid_png(size, rgb) -> bytes:
    from io import BytesIO
    buffer = BytesIO()
    Image.new("RGB", size, rgb).save(buffer, format="PNG")
    return buffer.getvalue()


def test_public_screenshot_returns_the_compositors_pixels_on_wayland():
    """The regression this whole seam exists for.

    ``je_auto_control.screenshot()`` used to call ImageGrab, so on Wayland it
    returned the XWayland root — blank — while the backend's grim capture was
    unreachable. Drive the real public entry point with a Wayland backend and
    a stubbed grim, and the bytes that come back have to be grim's.
    """
    import subprocess

    from je_auto_control.linux_wayland import capture as wayland_capture
    from je_auto_control.linux_wayland import screen as wayland_screen
    from je_auto_control.wrapper.auto_control_screen import screenshot

    png = _solid_png((3, 2), (10, 20, 30))

    def fake_grim(argv, **_kwargs):
        assert argv[0] == "/usr/bin/grim"
        return subprocess.CompletedProcess(argv, 0, png, b"")  # nosemgrep

    with patch.object(screen_grabber, "backend_grab_image",
                      return_value=wayland_screen.grab_image), \
         patch.object(wayland_capture, "binary_path",
                      return_value="/usr/bin/grim"), \
         patch.object(wayland_capture.subprocess, "run",
                      side_effect=fake_grim):
        frame = screenshot()

    # The wrapper hands back BGR for OpenCV, so RGB (10, 20, 30) arrives
    # reversed — proof these are grim's pixels and not an empty grab.
    assert frame.shape == (2, 3, 3)
    assert tuple(int(v) for v in frame[0][0]) == (30, 20, 10)


def test_mss_grabber_grabs_the_requested_monitor_rectangle():
    backend = _FakeBackendScreen()
    with _with_backend(backend):
        with screen_grabber.mss_grabber() as sct:
            shot = sct.grab({"left": 5, "top": 6, "width": 3, "height": 4})
    assert backend.calls == [[5, 6, 8, 10]]
    assert (shot.left, shot.top) == (5, 6)
