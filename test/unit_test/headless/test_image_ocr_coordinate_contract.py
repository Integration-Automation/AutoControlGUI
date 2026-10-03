"""Image/OCR matches must stay inside captured desktop coordinates."""
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PIL import Image

from je_auto_control.utils.exception.exceptions import AutoControlScreenException, ImageNotFoundException


@pytest.fixture
def textured_screen(monkeypatch):
    from je_auto_control.utils.cv2_utils import template_detection
    gray = np.random.default_rng(314).integers(0, 256, (14, 16), dtype=np.uint8)
    template = gray[4:9, 3:8].copy()
    screen = Image.fromarray(gray).convert('RGB')
    monkeypatch.setattr(template_detection, 'grab_logical', lambda *a, **k: (screen, -10, -20))
    return template_detection, template


def test_unicode_template_path(textured_screen, tmp_path, monkeypatch):
    detection, template = textured_screen
    path = tmp_path / '測試樣板.png'
    Image.fromarray(template).save(path)
    # Reproduce Windows' C-locale imread failure without a real desktop.
    monkeypatch.setattr(cv2, 'imread', lambda *a, **k: None)
    assert detection.find_image(path) == [True, [-7, -16, -2, -11]]


@pytest.mark.parametrize('as_pil', [False, True])
def test_grayscale_template(textured_screen, as_pil):
    detection, template = textured_screen
    value = Image.fromarray(template) if as_pil else template
    assert detection.find_image(value) == [True, [-7, -16, -2, -11]]


def test_corrupt_template_error_has_framework_type(textured_screen, monkeypatch):
    detection, template = textured_screen
    def fail(*args):
        raise cv2.error('synthetic matching failure')
    monkeypatch.setattr(cv2, 'matchTemplate', fail)
    with pytest.raises(ImageNotFoundException):
        detection.find_image(Image.fromarray(template).convert('RGB'))


def test_empty_image_file_has_the_documented_error(tmp_path):
    from je_auto_control.utils.cv2_utils.image_file import read_image
    path = tmp_path / 'empty.png'
    path.write_bytes(b'')
    with pytest.raises(ValueError):
        read_image(path, cv2.IMREAD_GRAYSCALE)


def test_partial_ocr_left_span_preserved():
    from je_auto_control.utils.ocr.text_span import find_spans
    boxes = [SimpleNamespace(text='unrelated prefix ' * 8 + 'Save', x=0, y=0, width=400, height=20),
             SimpleNamespace(text='As', x=410, y=0, width=30, height=20)]
    assert find_spans(boxes, 'Save As') == [boxes]


def test_negative_center_floor(monkeypatch):
    from je_auto_control.wrapper import auto_control_image as image
    monkeypatch.setattr(image.template_detection, 'find_image', lambda *a: [True, [-4, -4, 1, 1]])
    assert image.locate_image_center('fake') == (-2, -2)


def test_negative_click_center_floor(monkeypatch):
    from je_auto_control.wrapper import auto_control_image as image
    points = []
    monkeypatch.setattr(image.template_detection, 'find_image', lambda *a: [True, [-4, -4, 1, 1]])
    monkeypatch.setattr(image, 'set_mouse_position', lambda *args: points.append(args))
    monkeypatch.setattr(image, 'click_mouse', lambda *args: None)
    assert image.locate_and_click('fake', 'mouse_left') == (-2, -2)
    assert points == [(-2, -2)]


def _capture_env(monkeypatch):
    from je_auto_control.utils.monitor_layout import logical_frame
    monkeypatch.setattr(logical_frame, 'sys', SimpleNamespace(platform='win32'))
    calls = []
    def grab(**kwargs):
        calls.append(kwargs)
        return Image.new('RGB', (8, 8), (255, 255, 255))
    def metrics(index):
        return {76: -4, 77: -4, 78: 8, 79: 8}[index]
    return logical_frame, SimpleNamespace(grab=grab), metrics, calls


@pytest.mark.parametrize('region', [(0, 0, 0, 1), (0, 0, 1, -1), (0, 0, 1),
                                   (0, 0, float('inf'), 1), (-99, -99, 1, 1)])
def test_empty_region_rejected_before_capture(monkeypatch, region):
    frame, grabber, metrics, calls = _capture_env(monkeypatch)
    with pytest.raises(AutoControlScreenException):
        frame.grab_logical(region, grabber=grabber, metrics=metrics)
    assert calls == []


def test_partial_region_is_clipped_without_black_padding(monkeypatch):
    frame, grabber, metrics, _calls = _capture_env(monkeypatch)
    image, x, y = frame.grab_logical((-6, -6, 5, 5), grabber=grabber, metrics=metrics)
    assert image.size == (3, 3)
    assert (x, y) == (-4, -4)
    assert np.all(np.asarray(image) == 255)


def test_macos_region_is_clipped_in_global_points(monkeypatch):
    frame, grabber, _metrics, calls = _capture_env(monkeypatch)
    monkeypatch.setattr(frame, 'sys', SimpleNamespace(platform='darwin'))
    monkeypatch.setattr(frame, '_mac_display_rects', lambda: [(0, 0, 8, 8)])
    image, x, y = frame.grab_logical((-2, -2, 5, 5), grabber=grabber)
    assert image.size == (3, 3)
    assert (x, y) == (0, 0)
    assert calls == [{'bbox': (0, 0, 3, 3)}]


def test_linux_public_region_uses_the_clipped_frame(monkeypatch):
    from je_auto_control.utils.cv2_utils import screenshot
    frame, grabber, _metrics, calls = _capture_env(monkeypatch)
    monkeypatch.setattr(screenshot, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(screenshot, 'image_grabber', lambda: grabber)
    monkeypatch.setattr(frame, 'logical_virtual_rect', lambda metrics=None: (-4, -4, 8, 8))
    image = screenshot.pil_screenshot(screen_region=[-6, -6, -1, -1])
    assert image.size == (3, 3)
    assert calls == [{'all_screens': True}]


def test_public_bbox_infinity_is_a_screen_error(monkeypatch):
    from je_auto_control.utils.cv2_utils import screenshot
    _frame, grabber, _metrics, calls = _capture_env(monkeypatch)
    monkeypatch.setattr(screenshot, 'image_grabber', lambda: grabber)
    with pytest.raises(AutoControlScreenException):
        screenshot.pil_screenshot(screen_region=[0, 0, float('inf'), 1])
    assert calls == []
