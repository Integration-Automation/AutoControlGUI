"""Matchers report screen coordinates, not frame-local ones (2026-09-24 audit).

``match_masked``, ``match_masked_all``, ``match_subpixel``, ``match_auto``
and ``detect_scale`` dropped the captured frame's origin, so with a region
(or a virtual desktop starting at a negative x) they answered off by that
offset; golden-image capture cropped in physical pixels on a scaled display.
Captures are faked.
"""
import numpy as np
import pytest

from je_auto_control.utils.monitor_layout import logical_frame
from je_auto_control.utils.visual_match import visual_match

REGION = (100, 30, 80, 50)
TRUE_X, TRUE_Y = 120, 40


def _screen():
    rng = np.random.default_rng(7)
    screen = rng.integers(0, 60, size=(200, 300), dtype=np.uint8)
    screen[TRUE_Y:TRUE_Y + 20, TRUE_X:TRUE_X + 30] = rng.integers(
        100, 255, size=(20, 30), dtype=np.uint8)
    return screen


SCREEN = _screen()
TEMPLATE = SCREEN[TRUE_Y:TRUE_Y + 20, TRUE_X:TRUE_X + 30].copy()


@pytest.fixture(autouse=True)
def fake_capture(monkeypatch):
    from PIL import Image

    def grab(region=None, **_kwargs):
        x, y, width, height = region
        crop = SCREEN[y:y + height, x:x + width]
        return Image.fromarray(crop).convert("RGB"), x, y

    monkeypatch.setattr(logical_frame, "grab_logical", grab)


def test_masked_matches_are_in_screen_coordinates():
    match = visual_match.match_masked(TEMPLATE, region=REGION, min_score=0.9)
    assert (match.x, match.y) == (TRUE_X, TRUE_Y)
    assert [(m.x, m.y) for m in visual_match.match_masked_all(
        TEMPLATE, region=REGION, min_score=0.99)] == [(TRUE_X, TRUE_Y)]


def test_subpixel_auto_and_scale_matches_are_in_screen_coordinates():
    from je_auto_control.utils.match_autothresh.match_autothresh import match_auto
    from je_auto_control.utils.scale_detect.scale_detect import detect_scale
    from je_auto_control.utils.subpixel_match.subpixel_match import match_subpixel
    sub = match_subpixel(TEMPLATE, region=REGION, min_score=0.9)
    assert (sub.x, sub.y) == (TRUE_X, TRUE_Y)
    assert abs(sub.cx - (TRUE_X + 15)) < 1 and abs(sub.cy - (TRUE_Y + 10)) < 1
    assert (match_auto(TEMPLATE, region=REGION)[0].x, match_auto(TEMPLATE, region=REGION)[0].y) == (
        TRUE_X, TRUE_Y)
    best = detect_scale(TEMPLATE, region=REGION, scales=[1.0])
    assert best["center"] == [TRUE_X + 15, TRUE_Y + 10]


def test_golden_capture_uses_mouse_coordinates(tmp_path):
    from je_auto_control.utils.visual_regression import compare
    path = compare.take_golden(str(tmp_path / "g.png"), region=REGION)
    from PIL import Image
    saved = np.asarray(Image.open(path).convert("L"))
    assert saved.shape == (REGION[3], REGION[2])
    assert np.array_equal(saved, SCREEN[30:80, 100:180])
