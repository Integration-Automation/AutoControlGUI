"""One pixel of a capture is one coordinate for the mouse, on every monitor.

No real screen is read here: ``ImageGrab``, ``GetSystemMetrics``, ``user32`` and
Quartz are all fakes.

* Windows asked for *system* DPI awareness, so a monitor at a different scale
  from the primary one was virtualised. The process now asks for per-monitor-v2
  first and falls back.
* ``pil_screenshot(screen_region=...)`` — and with it ``screenshot``,
  ``AC_screenshot``, ``keyword_screenshot`` and ``capture_window`` — captured
  the primary monitor and cropped that, so a region on a monitor left of or
  above it was black.
* ``mark_screen`` drew its marks on a primary-monitor screenshot.
* ``grab_logical`` cropped a region that ran off the desktop without clipping
  it, so the padding could hold a "hit"; a negative size raised ``ValueError``.
* On macOS ``grab_logical`` returned Retina pixels and the main display only.
"""
import ctypes
import sys
import types

import pytest
from PIL import Image

from je_auto_control.utils.cv2_utils import region_capture, screenshot
from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.utils.monitor_layout import grab_logical, logical_frame, macos_frame
from je_auto_control.utils.set_of_marks import set_of_marks

_WINDOWS = sys.platform in ("win32", "cygwin", "msys")
windows_only = pytest.mark.skipif(not _WINDOWS, reason="the Win32 modules import on Windows only")

_WHITE, _RED, _BLUE, _BLACK = (255, 255, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0)
_LEFT_MONITOR = [-1920, 0, -1720, 100]


# --- Windows: DPI awareness --------------------------------------------------

def _user32(calls, per_monitor=1, system=1, awareness=2):
    """A ``user32`` recording which awareness was asked for.

    Plain functions, not methods: the module sets ``argtypes`` on what it
    calls, as it has to on the real thing.
    """
    def set_context(context):
        # A handle is pointer-width and unsigned; -4 is how the SDK spells it.
        calls.append(("context", ctypes.c_ssize_t(context.value).value))
        return per_monitor

    def set_aware():
        calls.append(("system",))
        return system

    return types.SimpleNamespace(
        SetProcessDpiAwarenessContext=set_context, SetProcessDPIAware=set_aware,
        GetThreadDpiAwarenessContext=lambda: 1,
        GetAwarenessFromDpiAwarenessContext=lambda context: awareness)


@pytest.fixture
def win32_screen(monkeypatch):
    from je_auto_control.windows.screen import win32_screen as module
    monkeypatch.setattr(module, "_dpi_awareness_requested", False)
    return module


@windows_only
def test_per_monitor_v2_is_asked_for_first(win32_screen):
    calls = []
    assert win32_screen.enable_dpi_awareness(_user32(calls)) == "per_monitor"
    assert calls == [("context", -4)], "no fallback once per-monitor was granted"


@windows_only
def test_a_refused_request_falls_back_to_system_awareness(win32_screen):
    """Refused when something set the awareness first; that must not raise."""
    calls = []
    answer = win32_screen.enable_dpi_awareness(_user32(calls, per_monitor=0, awareness=1))
    assert calls == [("context", -4), ("system",)]
    assert answer == "system"


@windows_only
def test_an_older_windows_without_the_function_falls_back(win32_screen):
    calls = []
    fake = _user32(calls, awareness=1)
    del fake.SetProcessDpiAwarenessContext
    assert win32_screen.enable_dpi_awareness(fake) == "system"
    assert calls == [("system",)]


@windows_only
def test_awareness_is_requested_once_per_process(win32_screen):
    calls = []
    fake = _user32(calls)
    win32_screen.enable_dpi_awareness(fake)
    win32_screen.enable_dpi_awareness(fake)
    assert calls == [("context", -4)]


@windows_only
def test_a_system_that_can_do_neither_is_not_an_error(win32_screen):
    def refuse(*_args):
        raise OSError("no such entry point")

    fake = types.SimpleNamespace(SetProcessDpiAwarenessContext=refuse, SetProcessDPIAware=refuse)
    assert win32_screen.enable_dpi_awareness(fake) == "unknown"


@windows_only
def test_importing_the_package_left_the_process_dpi_aware():
    """Read-only: whatever set it, this process is not unaware after the import."""
    from je_auto_control.windows.screen import win32_screen as module
    assert module.dpi_awareness() in ("system", "per_monitor")


# --- Windows: a region on another monitor ------------------------------------

class _Desktop:
    """``ImageGrab`` as on Windows: a bbox crops the primary monitor, ``all_screens`` spans both.

    The primary monitor is at (0, 0); a second one is to its left and holds a
    red block at (-1900, 10) to (-1800, 60).
    """

    def __init__(self, block=_RED):
        self.image = Image.new("RGB", (3840, 1080), _WHITE)
        if block:
            self.image.paste(block, (20, 10, 120, 60))

    def grab(self, bbox=None, all_screens=False, **_kwargs):
        image, (x0, y0) = (self.image, (-1920, 0)) if all_screens \
            else (self.image.crop((1920, 0, 3840, 1080)), (0, 0))
        if bbox:
            left, top, right, bottom = bbox
            image = image.crop((left - x0, top - y0, right - x0, bottom - y0))
        return image.copy()


def _metrics(index):
    return {76: -1920, 77: 0, 78: 3840, 79: 1080}[index]


@pytest.fixture
def desktop(monkeypatch):
    """Windows with a monitor left of the primary one."""
    grabber = _Desktop()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(logical_frame, "_system_metrics", _metrics)
    monkeypatch.setattr(logical_frame, "_load_image_grab", lambda: grabber)
    monkeypatch.setattr(screenshot, "image_grabber", lambda: grabber)
    return grabber


def test_negative_secondary_monitor_capture(desktop):
    image = screenshot.pil_screenshot(screen_region=_LEFT_MONITOR)
    assert image.size == (200, 100)
    assert image.getpixel((50, 30)) == _RED, "the block at (-1870, 30)"
    captured_secondary_is_black = image.getpixel((50, 30)) == _BLACK
    assert captured_secondary_is_black is False


def test_screenshot_and_its_keyword_see_the_other_monitor(desktop, tmp_path):
    pytest.importorskip("cv2")
    from je_auto_control.utils.pytest_plugin.keywords import keyword_screenshot
    from je_auto_control.wrapper.auto_control_screen import screenshot as wrapper_screenshot
    frame = wrapper_screenshot(screen_region=_LEFT_MONITOR)
    assert frame.shape[:2] == (100, 200)
    assert tuple(int(value) for value in frame[30, 50]) == (0, 0, 255), "red, as BGR"
    target = tmp_path / "keyword.png"
    keyword_screenshot(str(target), region=_LEFT_MONITOR)
    with Image.open(target) as saved:
        assert saved.convert("RGB").getpixel((50, 30)) == _RED


def test_a_window_on_the_other_monitor_is_captured(desktop, tmp_path):
    pytest.importorskip("cv2")
    from je_auto_control.utils.window_capture import capture_window
    target = tmp_path / "window.png"
    assert capture_window("Editor", target, geometry=lambda title: (-1920, 0, 200, 100)) == str(target)
    with Image.open(target) as saved:
        assert saved.size == (200, 100)
        assert saved.convert("RGB").getpixel((50, 30)) == _RED


def test_a_region_running_off_the_desktop_keeps_its_size_and_corner(desktop):
    """Still ``right - left`` wide, so a point in it is ``left`` plus its x."""
    image = screenshot.pil_screenshot(screen_region=[-2020, 0, -1720, 100])
    assert image.size == (300, 100)
    assert image.getpixel((50, 30)) == _BLACK, "left of every monitor"
    assert image.getpixel((150, 30)) == _RED, "the block, 100 px further in"
    assert region_capture.grab_screen_region([-2020, 0, -1720, 100]).size == (300, 100)


def test_a_region_off_every_monitor_is_refused(desktop):
    with pytest.raises(AutoControlScreenException, match="off screen"):
        screenshot.pil_screenshot(screen_region=[5000, 5000, 5100, 5100])


# --- grab_logical: clipping --------------------------------------------------

def test_a_located_region_is_clipped_to_the_desktop(desktop):
    """The origin handed back is the clipped one, so a hit maps to a real pixel."""
    image, origin_x, origin_y = grab_logical((-2020, -50, 300, 150), grabber=desktop,
                                             metrics=_metrics)
    assert (image.size, origin_x, origin_y) == ((200, 100), -1920, 0)
    assert image.getpixel((50, 30)) == _RED


@pytest.mark.parametrize("region", [(0, 0, -10, 10), (0, 0, 10, 0), (0, 0, 10), "nope"])
def test_empty_region_rejected(desktop, monkeypatch, region):
    """Before any capture, and as a framework error rather than a ValueError."""
    captured = []
    monkeypatch.setattr(desktop, "grab", lambda **kwargs: captured.append(kwargs))
    with pytest.raises(AutoControlScreenException):
        grab_logical(region, grabber=desktop, metrics=_metrics)
    assert captured == []


def test_a_region_inside_the_desktop_is_untouched(desktop):
    image, origin_x, origin_y = grab_logical((-1900, 10, 100, 50), grabber=desktop,
                                             metrics=_metrics)
    assert (image.size, origin_x, origin_y) == ((100, 50), -1900, 10)


# --- set-of-marks ------------------------------------------------------------

def test_marks_include_virtual_origin(monkeypatch, tmp_path):
    from je_auto_control.utils.accessibility import accessibility_api
    grabber = _Desktop(block=None)
    monkeypatch.setattr(logical_frame, "_system_metrics", _metrics)
    monkeypatch.setattr(logical_frame, "_load_image_grab", lambda: grabber)
    elements =[{"bbox": [-1900, 10, 100, 50], "role": "button", "text": "left monitor"},
                {"bbox": [300, 400, 100, 50], "role": "button", "text": "primary"}]
    monkeypatch.setattr(accessibility_api, "list_accessibility_elements",
                        lambda app_name=None: elements)
    target = tmp_path / "marks.png"
    result = set_of_marks.mark_screen(render_path=str(target))

    marked_points = [mark["center"] for mark in result["marks"]]
    expected_global_points = [[-1850, 35], [350, 425]]
    assert marked_points == expected_global_points, "marks stay in screen coordinates"
    assert result["image_origin"] == [-1920, 0]
    with Image.open(target) as saved:
        picture = saved.convert("RGB")
        assert picture.size == (3840, 1080), "every monitor, not the primary one"
        assert picture.getpixel((20 + 100, 10 + 25)) == _RED, "the left monitor's box edge"
        assert picture.getpixel((1920 + 300 + 100, 400 + 25)) == _RED, "the primary's box edge"
        assert picture.getpixel((300 + 100, 400 + 25)) == _WHITE, "not drawn 1920 px to the left"


def test_render_marks_takes_the_images_origin():
    import io
    blank = io.BytesIO()
    Image.new("RGB", (400, 200), _WHITE).save(blank, format="PNG")
    marks = set_of_marks.mark_elements([{"bbox": [-150, 20, 100, 50]}])
    with Image.open(io.BytesIO(set_of_marks.render_marks(blank.getvalue(), marks,
                                                         origin=(-200, 0)))) as picture:
        assert picture.convert("RGB").getpixel((50 + 100, 20 + 25)) == _RED


# --- macOS -------------------------------------------------------------------

_MAIN = (0, 0, 1440, 900)            # Retina: 2880 x 1800 device pixels
_LEFT = (-1920, 0, 1920, 1080)       # a 1x display to its left
_DISPLAYS = [_MAIN, _LEFT]


class _ScreenCapture:
    """``ImageGrab`` as on macOS: ``screencapture -R`` in points, Retina at 2x.

    The desktop, in points, is white with a blue block at (100, 50)-(140, 70) on
    the Retina main display and a red one at (-1900, 10)-(-1800, 60) on the 1x
    display. A capture comes back in device pixels unless ``scale_down`` is set,
    and a capture with no rectangle is the main display only.
    """

    def __init__(self):
        self.world = Image.new("RGB", (3360, 1080), _BLACK)
        self.world.paste(_WHITE, (0, 0, 1920, 1080))
        self.world.paste(_WHITE, (1920, 0, 3360, 900))
        self.world.paste(_BLUE, (1920 + 100, 50, 1920 + 140, 70))
        self.world.paste(_RED, (20, 10, 120, 60))
        self.rectangles = []

    def grab(self, bbox=None, all_screens=False, scale_down=False, **_kwargs):
        left, top, right, bottom = bbox or (0, 0, 1440, 900)
        self.rectangles.append(bbox)
        points = self.world.crop((left + 1920, top, right + 1920, bottom))
        scale = 1 if scale_down or left < 0 else 2
        return points.resize((points.width * scale, points.height * scale))


def _displays():
    return list(_DISPLAYS)


def test_retina_maps_to_points():
    """A target found in the frame is where the mouse has to go, not twice as far."""
    capture = _ScreenCapture()
    image, origin_x, origin_y = grab_logical(None, grabber=capture, displays=_displays)
    assert (image.size, origin_x, origin_y) == ((3360, 1080), -1920, 0)
    found = next((x, y) for y in range(40, 80) for x in range(1920, 2100)
                 if image.getpixel((x, y)) == _BLUE)
    logical_click = (found[0] + origin_x, found[1] + origin_y)
    assert logical_click == (100, 50)


def test_the_second_display_is_in_the_macos_frame():
    image, origin_x, _origin_y = grab_logical(None, grabber=_ScreenCapture(), displays=_displays)
    assert image.getpixel((-1870 - origin_x, 30)) == _RED
    assert image.getpixel((3000, 1000)) == _BLACK, "below the shorter display: no screen there"


def test_a_macos_region_is_captured_in_points():
    capture = _ScreenCapture()
    image, origin_x, origin_y = grab_logical((90, 40, 100, 60), grabber=capture, displays=_displays)
    assert (image.size, origin_x, origin_y) == ((100, 60), 90, 40)
    assert image.getpixel((10, 10)) == _BLUE and image.getpixel((5, 5)) == _WHITE
    assert capture.rectangles == [(90, 40, 190, 100)]


def test_a_macos_region_across_two_displays_is_stitched():
    capture = _ScreenCapture()
    image, origin_x, _origin_y = grab_logical((-1900, 0, 2100, 100), grabber=capture,
                                              displays=_displays)
    assert (image.size, origin_x) == ((2100, 100), -1900)
    assert image.getpixel((30, 30)) == _RED, "(-1870, 30) on the 1x display"
    assert image.getpixel((1900 + 110, 60)) == _BLUE, "(110, 60) on the Retina display"
    assert sorted(capture.rectangles) == [(-1900, 0, 0, 100), (0, 0, 200, 100)]


def test_a_macos_region_is_clipped_to_the_displays():
    image, origin_x, origin_y = grab_logical((-2000, -30, 200, 100), grabber=_ScreenCapture(),
                                             displays=_displays)
    assert (image.size, origin_x, origin_y) == ((120, 70), -1920, 0)
    with pytest.raises(AutoControlScreenException, match="off screen"):
        grab_logical((9000, 0, 10, 10), grabber=_ScreenCapture(), displays=_displays)


def test_the_macos_primary_only_frame_is_in_points_too():
    image, origin_x, origin_y = grab_logical(None, all_screens=False, grabber=_ScreenCapture(),
                                             displays=_displays)
    assert (image.size, origin_x, origin_y) == ((1440, 900), 0, 0)
    assert image.getpixel((110, 60)) == _BLUE


def test_without_quartz_the_generic_capture_is_used():
    """No pyobjc: the frame is whatever the grabber returns, as before."""
    def no_quartz():
        raise ImportError("No module named 'Quartz'")

    capture = _ScreenCapture()
    assert macos_frame.grab_macos(capture, None, displays=no_quartz) is None
    image, origin_x, origin_y = grab_logical(None, grabber=capture, displays=no_quartz,
                                             metrics=lambda index: 0)
    assert (image.size, origin_x, origin_y) == ((2880, 1800), 0, 0)


def test_only_pillows_own_grabber_takes_the_macos_path(monkeypatch):
    """A backend's or a test's grabber is not ``screencapture`` and is left alone."""
    from PIL import ImageGrab
    monkeypatch.setattr(logical_frame, "_is_macos", lambda: True)
    assert logical_frame._is_pillow_grab(ImageGrab) is True
    capture = _ScreenCapture()
    grab_logical(None, grabber=capture, metrics=lambda index: 0)
    assert capture.rectangles == [None], "one plain capture, no per-display rectangles"


def test_display_bounds_are_read_from_quartz(monkeypatch):
    def bounds(display_id):
        x, y, width, height = {1: _MAIN, 2: _LEFT}[display_id]
        return types.SimpleNamespace(origin=types.SimpleNamespace(x=float(x), y=float(y)),
                                     size=types.SimpleNamespace(width=float(width),
                                                                height=float(height)))

    quartz = types.SimpleNamespace(
        CGGetActiveDisplayList=lambda limit, displays, count: (0, (1, 2), 2),
        CGDisplayBounds=bounds)
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    assert macos_frame.quartz_display_bounds() == _DISPLAYS
    quartz.CGGetActiveDisplayList = lambda limit, displays, count: (1001, (), 0)
    assert macos_frame.quartz_display_bounds() == []


def test_the_main_display_is_the_one_at_the_origin():
    assert macos_frame.main_display([_LEFT, _MAIN]) == _MAIN
    assert macos_frame.display_union(_DISPLAYS) == (-1920, 0, 3360, 1080)
