"""R3 regression: RGB vs BGR luminance weights + bounded find-all. No Qt.

Covers:
* visual_match._to_gray / ssim._to_gray_f converting ndarray / PIL (RGB) sources
  with BGR weights, which swapped the R/B luminance weights so a red template's
  gray disagreed with the same red on screen by up to ~47/255.
* best_matches materialising a Match per score-map position (min_score=-1.0),
  effectively hanging on a real screen.
"""
import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.visual_match import visual_match as vm   # noqa: E402
from je_auto_control.utils.ssim import ssim as ssim_mod             # noqa: E402
from je_auto_control.utils.ssim.ssim import ssim_compare            # noqa: E402


# Correct luminance of saturated red: 0.299 * 255. The old BGR-on-RGB path gave
# 0.114 * 255 ~= 29 (the blue weight).
_RED_GRAY = 0.299 * 255


def _rgb_red(height: int = 8, width: int = 8):
    """A saturated-red image in RGB channel order (R in channel 0)."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[..., 0] = 255
    return img


def test_visual_match_gray_uses_rgb_weights_for_ndarray():
    gray = vm._to_gray(_rgb_red())
    assert gray.mean() == pytest.approx(_RED_GRAY, abs=1.0)


def test_visual_match_gray_uses_rgb_weights_for_pil():
    pytest.importorskip("PIL")
    from PIL import Image
    gray = vm._to_gray(Image.fromarray(_rgb_red()))   # PIL is RGB
    assert gray.mean() == pytest.approx(_RED_GRAY, abs=1.0)


def test_disk_bgr_template_and_rgb_haystack_agree(tmp_path):
    # A red image written to disk is read back as BGR by cv2.imread; the same
    # red as an RGB ndarray (the live screen grab) must map to the same gray.
    path = tmp_path / "red.png"
    cv2.imwrite(str(path), np.full((8, 8, 3), (0, 0, 255), np.uint8))  # BGR red
    from_disk = vm._to_gray(str(path))
    from_rgb = vm._to_gray(_rgb_red())
    assert from_disk.mean() == pytest.approx(from_rgb.mean(), abs=1.0)
    assert from_disk.mean() == pytest.approx(_RED_GRAY, abs=1.0)


def test_ssim_gray_uses_rgb_weights_for_ndarray():
    gray = ssim_mod._to_gray_f(_rgb_red())
    assert float(gray.mean()) == pytest.approx(_RED_GRAY, abs=1.0)


def test_ssim_compare_disk_red_vs_rgb_red_is_identical(tmp_path):
    path = tmp_path / "red.png"
    cv2.imwrite(str(path), np.full((20, 20, 3), (0, 0, 255), np.uint8))
    score = ssim_compare(str(path), _rgb_red(20, 20))
    # Structurally identical red -> ~1.0. The old code read them ~47 apart,
    # scoring the identical colour as a large structural change (~0.67).
    assert score > 0.99


def _textured(height: int, width: int, seed: int = 0):
    yy, xx = np.mgrid[0:height, 0:width]
    return ((yy * 53 + xx * 97 + yy * xx * 17 + seed) % 256).astype(np.uint8)


def test_best_matches_is_bounded(monkeypatch):
    """best_matches must cap candidates before the O(n·kept) Python NMS."""
    hay = _textured(200, 300, seed=5)
    tmpl = hay[40:52, 60:72].copy()          # an exact 12x12 sub-patch

    built = {"n": 0}
    real_match = vm.Match

    def counting_match(*args, **kwargs):
        built["n"] += 1
        return real_match(*args, **kwargs)

    monkeypatch.setattr(vm, "Match", counting_match)
    result = vm.best_matches(tmpl, haystack=hay, top_n=5)

    assert len(result) <= 5
    assert (result[0].x, result[0].y) == (60, 40)   # correctness preserved
    # ~54k positions clear min_score=-1.0; the cap keeps construction bounded.
    assert built["n"] <= 1000
