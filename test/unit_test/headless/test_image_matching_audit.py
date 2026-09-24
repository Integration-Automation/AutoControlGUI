"""Image-matching defects from the 2026-09-24 audit (synthetic numpy images, no screen).

Several matchers dropped the screen-grab origin; rotated templates were
correlated with their black padding and sqdiff picked the worst spot; flat
templates "matched" at (0, 0) off the score-map paths; auto-threshold took a
neighbouring blob's peak; ORB with 1-3 matches raised cv2.error; palette and
"LA" PIL images were read wrongly; a negative best peak gave a nonsense ratio.
"""
import cv2
import numpy as np
import pytest

from je_auto_control.utils.edge_lines.edge_lines import find_lines
from je_auto_control.utils.exception.exceptions import AutoControlFlatTemplateException
from je_auto_control.utils.feature_match.feature_match import feature_match
from je_auto_control.utils.match_autothresh import match_autothresh
from je_auto_control.utils.match_trust.match_trust import _peak_stats, match_with_trust
from je_auto_control.utils.rotated_match.rotated_match import _rotate, match_rotated
from je_auto_control.utils.shape_locator.shape_locator import find_shapes
from je_auto_control.utils.subpixel_match.subpixel_match import match_subpixel
from je_auto_control.utils.visual_match import visual_match

RNG = np.random.default_rng(7)


def _textured(size=30):
    return RNG.integers(0, 255, (size, size), dtype=np.uint8)


@pytest.fixture
def offset_screen(monkeypatch):
    """A fake screen grab whose frame starts at (500, 300)."""
    def install(gray):
        monkeypatch.setattr(visual_match, "_grab_gray_with_origin",
                            lambda _region: (gray, 500, 300))
    return install


def test_rotated_matches_on_a_light_background_and_report_screen_coordinates(offset_screen):
    template = _textured()
    rotated = _rotate(template, 30.0)
    mask = _rotate(np.full_like(template, 255), 30.0)
    screen = np.full((200, 200), 255, np.uint8)
    height, width = rotated.shape
    screen[40:40 + height, 50:50 + width] = np.where(mask > 0, rotated, 255)
    offset_screen(screen)
    match = match_rotated(template, angles=(30.0,), min_score=0.9)
    assert match is not None and (match.x, match.y) == (550, 340)


def test_rotated_sqdiff_picks_the_best_spot():
    template = _textured()
    screen = np.full((120, 120), 255, np.uint8)
    screen[20:50, 60:90] = template
    match = match_rotated(template, haystack=screen, method="sqdiff_normed", min_score=0.9)
    assert (match.x, match.y) == (60, 20)


@pytest.mark.parametrize("finder", [
    lambda t, h: match_subpixel(t, haystack=h),
    lambda t, h: match_autothresh.match_auto(t, haystack=h),
    lambda t, h: match_with_trust(t, haystack=h),
    lambda t, h: match_rotated(t, haystack=h),
])
def test_a_flat_template_is_refused_everywhere(finder):
    flat = np.full((10, 10), 128, np.uint8)
    with pytest.raises(AutoControlFlatTemplateException):
        finder(flat, RNG.integers(0, 255, (60, 60), dtype=np.uint8))


def test_each_blob_reports_its_own_peak():
    scores = np.zeros((40, 40), np.float32)
    scores[5:30, 5:8] = 0.7     # an L-shaped blob whose box contains ...
    scores[27:30, 5:30] = 0.7
    scores[10, 20] = 0.95       # ... a separate high blob
    mask = (scores >= 0.6).astype(np.uint8)
    peaks = sorted(match_autothresh._blob_peaks(scores, mask), key=lambda p: -p[2])
    assert [round(score, 2) for _x, _y, score in peaks] == [0.95, 0.7]


def test_feature_match_with_few_matches_is_none_not_cv2_error(monkeypatch):
    import importlib
    module = importlib.import_module("je_auto_control.utils.feature_match.feature_match")
    keypoint = cv2.KeyPoint(1, 1, 1)
    good = [cv2.DMatch(0, 0, 0.1)] * 2
    monkeypatch.setattr(module, "_keypoint_matches",
                        lambda *_a: ([keypoint], [keypoint], good))
    assert feature_match(_textured(), haystack=_textured(), min_inliers=0) is None


def test_trust_uses_the_screen_origin(offset_screen):
    template = _textured()
    screen = RNG.integers(0, 255, (120, 120), dtype=np.uint8)
    screen[20:50, 60:90] = template
    offset_screen(screen)
    match = match_with_trust(template)
    assert (match.x, match.y) == (560, 320)


def test_shapes_and_lines_use_the_screen_origin(offset_screen):
    screen = np.zeros((200, 200), np.uint8)
    cv2.rectangle(screen, (40, 40), (120, 100), 255, -1)
    cv2.line(screen, (10, 180), (190, 180), 255, 2)
    offset_screen(screen)
    assert find_shapes()[0]["x"] >= 500
    assert all(line["x1"] >= 500 and line["y1"] >= 300 for line in find_lines())


def test_a_negative_best_peak_is_ambiguous_and_a_negative_second_is_not():
    scores = np.full((20, 20), -0.5, np.float32)
    scores[10, 10] = -0.2
    assert _peak_stats(scores, 3)[3] == 1.0
    scores[10, 10] = 0.9
    assert _peak_stats(scores, 3)[3] == 0.0


def test_palette_and_la_images_become_true_luminance():
    from PIL import Image
    palette = Image.new("P", (2, 1))
    palette.putpalette([255, 0, 0, 0, 0, 255] + [0] * 762)
    palette.putpixel((0, 0), 0)
    palette.putpixel((1, 0), 1)
    assert visual_match._to_gray(palette).tolist() == [[76, 29]]
    la = Image.new("LA", (2, 1), (200, 255))
    assert visual_match._to_gray(la).tolist() == [[200, 200]]
