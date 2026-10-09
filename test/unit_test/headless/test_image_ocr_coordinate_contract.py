"""Template reading, OCR span matching and centre arithmetic, on synthetic data.

From the 2026-09-24 audit: a template under a non-ASCII folder could not be
read (``cv2.imread`` goes through the C locale on Windows), a grayscale
template -- a 2-D array or a PIL ``"L"`` image -- raised ``cv2.error``, which
no caller catches, a target that began at the end of a long OCR box was never
found, and the centre of a hit left of or above the primary monitor was one
pixel off because ``int()`` cuts toward zero.

The screen is a synthetic frame; nothing is captured or clicked.
"""
import types

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("cv2")
pytest.importorskip("je_open_cv")

from je_auto_control.utils.cv2_utils import template_detection  # noqa: E402
from je_auto_control.utils.cv2_utils.image_file import write_image  # noqa: E402
from je_auto_control.utils.exception.exceptions import ImageNotFoundException  # noqa: E402
from je_auto_control.utils.ocr import text_span  # noqa: E402
from je_auto_control.wrapper import auto_control_image  # noqa: E402

_ORIGIN = (1000, 500)
_CROP = (130, 80, 170, 120)
_CENTRE = (1150, 600)


@pytest.fixture
def screen(monkeypatch):
    """A smooth blob centred at (150, 100) of a 300x200 frame, on screen at _ORIGIN."""
    yy, xx = np.mgrid[0:200, 0:300]
    blob = (255 * np.exp(-(((xx - 150) ** 2) / 400 + ((yy - 100) ** 2) / 300))).astype(np.uint8)
    frame = Image.fromarray(np.stack([blob] * 3, axis=-1))
    monkeypatch.setattr(template_detection, "grab_logical",
                        lambda region, all_screens=True: (frame.copy(), *_ORIGIN))
    return frame


def test_a_template_under_a_non_ascii_folder_is_read(screen, tmp_path):
    folder = tmp_path / "測試"
    folder.mkdir()
    path = folder / "樣板.png"
    write_image(path, np.asarray(screen.crop(_CROP)))
    assert auto_control_image.locate_image_center(str(path)) == _CENTRE
    assert auto_control_image.locate_image_center(path) == _CENTRE


def test_a_pil_grayscale_template_is_matched(screen):
    template = screen.crop(_CROP).convert("L")
    assert auto_control_image.locate_image_center(template) == _CENTRE


def test_a_two_dimensional_array_template_is_matched(screen):
    template = np.asarray(screen.crop(_CROP).convert("L"))
    assert template.ndim == 2
    assert auto_control_image.locate_image_center(template) == _CENTRE
    assert auto_control_image.locate_all_image(template, 0.95) == [[1130, 580, 1170, 620]]


def test_a_single_channel_three_dimensional_template_is_matched(screen):
    template = np.asarray(screen.crop(_CROP).convert("L"))[:, :, None]
    assert auto_control_image.locate_image_center(template) == _CENTRE


def test_a_colour_template_still_matches(screen):
    assert auto_control_image.locate_image_center(screen.crop(_CROP)) == _CENTRE
    assert auto_control_image.locate_image_center(np.asarray(screen.crop(_CROP))) == _CENTRE


@pytest.mark.parametrize("template", [
    np.zeros((5, 5, 2), dtype=np.uint8),        # no such colour layout
    np.zeros((5, 5), dtype=np.float64),         # a pixel type matchTemplate refuses
    np.zeros((2, 2, 2, 2), dtype=np.uint8),
])
def test_a_template_opencv_cannot_use_is_the_typed_miss(screen, template):
    with pytest.raises(ImageNotFoundException):
        auto_control_image.locate_image_center(template)


def test_an_undecodable_file_is_the_typed_miss(screen, tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"not an image")
    with pytest.raises(ImageNotFoundException, match="broken.png"):
        auto_control_image.locate_image_center(str(path))


# --- centre arithmetic ------------------------------------------------------

@pytest.mark.parametrize("box, centre", [
    ([-5, -5, 0, 0], (-3, -3)),         # pixels -5..-1: the middle one is -3
    ([-4, -9, -1, -2], (-3, -6)),
    ([0, 0, 5, 5], (2, 2)),             # the mirror image, unchanged
    ([10, 20, 30, 40], (20, 30)),
])
def test_the_centre_is_floored_on_both_sides_of_the_origin(monkeypatch, box, centre):
    monkeypatch.setattr(template_detection, "find_image", lambda *a, **k: [True, box])
    assert auto_control_image.locate_image_center("any") == centre


def test_locate_and_click_uses_the_same_centre(monkeypatch):
    moved, clicked = [], []
    monkeypatch.setattr(template_detection, "find_image",
                        lambda *a, **k: [True, [-5, -5, 0, 0]])
    monkeypatch.setattr(auto_control_image, "set_mouse_position",
                        lambda x, y: moved.append((x, y)))
    monkeypatch.setattr(auto_control_image, "click_mouse", clicked.append)
    assert auto_control_image.locate_and_click("any", "mouse_left") == (-3, -3)
    assert moved == [(-3, -3)]
    assert clicked == ["mouse_left"]


# --- OCR span matching ------------------------------------------------------

def _box(text, x):
    return types.SimpleNamespace(text=text, x=x, y=10, width=40, height=12)


_LONG = "Open the File menu at the top of the window and then choose"


def test_a_target_starting_at_the_end_of_a_long_box_is_found():
    assert len(text_span.normalize(_LONG + "Save")) > len("saveas") + text_span.MAX_OVERSHOOT
    boxes = [_box(_LONG + " Save", 0), _box("As", 500)]
    spans = text_span.find_spans(boxes, "Save As")
    assert [[box.text for box in span] for span in spans] == [[_LONG + " Save", "As"]]


def test_a_target_after_a_long_run_of_short_boxes_is_still_minimal():
    words = (_LONG * 2).split()
    boxes = [_box(word, 50 * index) for index, word in enumerate([*words, "Save", "As", "now"])]
    spans = text_span.find_spans(boxes, "Save As")
    assert [[box.text for box in span] for span in spans] == [["Save", "As"]]


def test_a_long_box_is_dropped_once_it_cannot_start_the_target():
    boxes = [_box(_LONG, 0), _box("Export", 500), _box("Save", 600), _box("As", 700)]
    spans = text_span.find_spans(boxes, "Save As")
    assert [[box.text for box in span] for span in spans] == [["Save", "As"]]
