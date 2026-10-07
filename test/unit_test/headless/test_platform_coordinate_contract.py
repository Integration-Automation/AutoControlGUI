"""Capture pixels, marks and input coordinates share one global space."""
import ctypes
from types import SimpleNamespace

from PIL import Image
import pytest

from je_auto_control.utils.monitor_layout import logical_frame as frame


def test_negative_secondary_monitor_capture(monkeypatch):
    from je_auto_control.utils.cv2_utils import screenshot as capture
    # This fixture supplies a Windows-style virtual frame; Retina is tested separately below.
    monkeypatch.setattr(frame, 'sys', SimpleNamespace(platform='win32'))
    virtual = Image.new('RGB', (300, 100), 'blue')
    virtual.paste('red', (0, 0, 100, 100))
    class Grabber:
        def grab(self, *, all_screens=False, bbox=None):
            if all_screens:
                return virtual.copy()
            return Image.new('RGB', (100, 100), 'black')
    grabber = Grabber()
    monkeypatch.setattr(capture, 'image_grabber', lambda: grabber)
    monkeypatch.setattr(frame, '_load_image_grab', lambda: grabber)
    monkeypatch.setattr(frame, 'logical_virtual_rect', lambda metrics=None: (-100, 0, 300, 100))
    image = capture.pil_screenshot(screen_region=[-80, 10, -20, 70])
    assert image.size == (60, 60)
    assert image.getpixel((30, 30)) == (255, 0, 0)


def test_retina_maps_to_points(monkeypatch):
    monkeypatch.setattr(frame, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(frame, '_mac_display_rects', lambda: [(0, 0, 200, 100)])
    class Retina:
        def grab(self, *, bbox=None, **kwargs):
            # A distinctive feature at pixel (200,100) is point (100,50).
            image = Image.new('RGB', (400, 200), 'white')
            image.paste('red', (190, 90, 210, 110))
            return image
    image, x, y = frame.grab_logical(grabber=Retina())
    assert image.size == (200, 100)
    assert (x, y) == (0, 0)
    assert image.getpixel((100, 50)) == (255, 0, 0)


def test_mixed_retina_and_negative_secondary_are_stitched_per_display(monkeypatch):
    monkeypatch.setattr(frame, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(frame, '_mac_display_rects', lambda: [(0, 0, 200, 100), (-100, -50, 100, 100)])
    class Displays:
        def grab(self, *, bbox=None, **kwargs):
            if bbox == (-100, -50, 0, 50):
                return Image.new('RGB', (100, 100), 'blue')
            return Image.new('RGB', (400, 200), 'red')
    image, x, y = frame.grab_logical(grabber=Displays())
    assert (x, y, image.width, image.height) == (-100, -50, 300, 150)
    assert image.getpixel((10, 10)) == (0, 0, 255)
    assert image.getpixel((150, 100)) == (255, 0, 0)


@pytest.mark.parametrize('primary_only', [True, False])
def test_public_mac_capture_supports_older_pillow_in_points(monkeypatch, primary_only):
    from je_auto_control.utils.cv2_utils import screenshot, region_capture, screen_grabber
    monkeypatch.setattr(__import__('sys'), 'platform', 'darwin')
    monkeypatch.setattr(frame, '_mac_display_rects', lambda: [(0, 0, 200, 100), (-100, 0, 100, 100)])
    class OlderPillow:
        def grab(self, *, bbox=None):
            width, height = (200, 100) if bbox is None else (bbox[2] - bbox[0], bbox[3] - bbox[1])
            return Image.new('RGB', (width * 2, height * 2), 'red')
    grabber = OlderPillow()
    monkeypatch.setattr(screenshot, 'image_grabber', lambda: grabber)
    monkeypatch.setattr(screen_grabber, 'image_grabber', lambda: grabber)
    monkeypatch.setattr(frame, '_load_image_grab', lambda: grabber)
    if primary_only:
        image = screenshot.pil_screenshot()
        assert image.size == (200, 100)
    else:
        image = region_capture.grab_screen_region([-80, 10, -20, 70])
        assert image.size == (60, 60)
    assert image.getpixel((10, 10)) == (255, 0, 0)


@pytest.mark.parametrize('platform, expected', [('win32', (-1880, -109, 75, 50)),
                                               ('darwin', (-1888, -120, 60, 40))])
def test_qt_regions_and_input_points_round_trip(monkeypatch, platform, expected):
    from PySide6.QtCore import QRect
    from je_auto_control.gui import _screen_geometry as geometry
    monkeypatch.setattr(geometry, 'sys', SimpleNamespace(platform=platform))
    screen = SimpleNamespace(geometry=lambda: QRect(-1920, -164, 1536, 864),
                             devicePixelRatio=lambda: 1.25)
    native = geometry.native_region(screen, QRect(32, 44, 60, 40))
    assert native == expected
    point = geometry.logical_point(screen, native[0], native[1])
    assert (point.x(), point.y()) == (-1888, -120)


def test_marks_include_virtual_origin(tmp_path, monkeypatch):
    from je_auto_control.utils.set_of_marks import set_of_marks as marks
    from je_auto_control.utils.accessibility import accessibility_api
    monkeypatch.setattr(accessibility_api, 'list_accessibility_elements',
                        lambda **kwargs: [{'bbox': [-90, -40, 30, 30]}])
    monkeypatch.setattr(frame, 'grab_logical',
                        lambda *args, **kwargs: (Image.new('RGB', (300, 150), 'white'), -100, -50))
    output = tmp_path / 'marked.png'
    result = marks.mark_screen(render_path=str(output))
    assert result['marks'][0]['center'] == [-75, -25]
    assert Image.open(output).getpixel((10, 30)) == (255, 0, 0)
    assert result['origin'] == [-100, -50]


@pytest.mark.skipif(__import__('sys').platform != 'win32', reason='Windows DLL module')
@pytest.mark.parametrize('v2_ok, expected', [(True, ['v2']), (False, ['v2', 'legacy'])])
def test_per_monitor_v2_precedes_legacy_fallback(v2_ok, expected):
    from je_auto_control.windows.screen import win32_screen
    calls = []
    class Function:
        def __init__(self, name, result):
            self.name, self.result = name, result
        def __call__(self, *args):
            calls.append(self.name)
            if args:
                assert args[0].value == ctypes.c_void_p(-4).value
            return self.result
    user32 = SimpleNamespace(SetProcessDpiAwarenessContext=Function('v2', v2_ok),
                             SetProcessDPIAware=Function('legacy', True))
    win32_screen._configure_dpi_awareness(user32)
    assert calls == expected
