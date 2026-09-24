"""Regression tests for the image-utility defects of the 2026-09-23 audit.

Grayscale treated PIL images and screen grabs (RGB) as BGR, palette images as
their indices, and deskew never saw light text on a dark background.
``cv2.imread`` / ``imwrite`` failed on non-ASCII paths. A red glyph could not
match even its exact copy, and ``color_region`` crashed on RGBA / L images. A
golden of another size raised instead of mismatching. An approval
``extension`` escaped ``approvals_dir``. Zero-area boxes were marked, unknown
hash names fell back to average hash, and duplicate elements collapsed in a
screen diff. All images are built in memory -- no screenshots, no input.
"""
import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
Image = pytest.importorskip("PIL.Image")

from je_auto_control.utils.approval.approval_test import verify_artifact  # noqa: E402
from je_auto_control.utils.color_match import match_color  # noqa: E402
from je_auto_control.utils.color_region.color_region import find_color_regions  # noqa: E402
from je_auto_control.utils.cv2_utils.image_file import read_image, write_image  # noqa: E402
from je_auto_control.utils.image_dedup.perceptual_hash import hamming_distance  # noqa: E402
from je_auto_control.utils.preprocess import preprocess as pre  # noqa: E402
from je_auto_control.utils.screen_state.screen_state import diff_snapshots  # noqa: E402
from je_auto_control.utils.set_of_marks.set_of_marks import mark_elements  # noqa: E402
from je_auto_control.utils.visual_regression.compare import compare_to_golden  # noqa: E402


@pytest.mark.parametrize("colour, expected", [((255, 0, 0), 76), ((0, 0, 255), 29)])
def test_grayscale_weights_red_and_blue_correctly(colour, expected):
    gray = pre.to_grayscale(Image.new("RGB", (4, 4), colour))
    assert abs(int(gray[0, 0]) - expected) <= 1


def test_a_screen_grab_is_converted_too(monkeypatch):
    from je_auto_control.utils.cv2_utils import screenshot
    monkeypatch.setattr(screenshot, "pil_screenshot",
                        lambda screen_region=None: Image.new("RGB", (4, 4), (255, 0, 0)))
    assert abs(int(pre.to_grayscale()[0, 0]) - 76) <= 1


def test_a_palette_image_is_read_by_colour_not_index():
    image = Image.new("P", (4, 4), 0)
    image.putpalette([255, 255, 255] + [0, 0, 0] * 255)
    assert int(pre.to_grayscale(image)[0, 0]) == 255


@pytest.mark.parametrize("scale", [0, -2, float("nan")])
def test_upscale_refuses_a_non_positive_scale(scale):
    with pytest.raises(ValueError):
        pre.upscale(np.zeros((4, 4), dtype=np.uint8), scale=scale)


def test_the_adaptive_steps_take_block_size_and_c():
    rng = np.random.default_rng(0)
    image = rng.integers(0, 255, (40, 40), dtype=np.uint8)
    first = pre.preprocess_image(image, steps=("adaptive_mean",), block_size=3, c=0)
    second = pre.preprocess_image(image, steps=("adaptive_mean",), block_size=31, c=40)
    assert not np.array_equal(first, second)


def _text_lines(dark_theme):
    background, ink = (0, 255) if dark_theme else (255, 0)
    image = np.full((200, 300), background, dtype=np.uint8)
    for row in range(40, 170, 25):
        cv2.line(image, (40, row), (260, row), ink, 4)
    matrix = cv2.getRotationMatrix2D((150, 100), 5, 1.0)
    return cv2.warpAffine(image, matrix, (300, 200), borderValue=background)


@pytest.mark.parametrize("dark_theme", [False, True])
def test_deskew_sees_light_and_dark_themes(dark_theme):
    assert abs(abs(pre.detect_skew_angle(_text_lines(dark_theme))) - 5) < 0.5


def test_non_ascii_paths_round_trip(tmp_path):
    path = tmp_path / "測試.png"
    write_image(path, np.full((3, 5, 3), 200, dtype=np.uint8))
    assert path.exists() and read_image(path, cv2.IMREAD_COLOR).shape == (3, 5, 3)
    assert pre.to_grayscale(str(path)).shape == (3, 5)


def _plus(colour):
    glyph = np.full((20, 20, 3), 255, dtype=np.uint8)
    glyph[8:12, :] = colour
    glyph[:, 8:12] = colour
    return glyph


def test_a_red_glyph_matches_its_copy_and_not_a_green_one():
    haystack = np.full((80, 120, 3), 255, dtype=np.uint8)
    haystack[30:50, 20:40] = _plus((255, 0, 0))
    haystack[30:50, 80:100] = _plus((0, 255, 0))
    match = match_color(_plus((255, 0, 0)), haystack=haystack, min_score=0.9)
    assert match is not None and (match.x, match.y) == (20, 30)


@pytest.mark.parametrize("mode", ["RGBA", "L"])
def test_color_regions_accept_any_pil_mode(mode):
    image = Image.new("RGB", (40, 40), (255, 255, 255)).convert(mode)
    assert find_color_regions((255, 255, 255), haystack=image, min_area=10)


def test_a_golden_of_another_size_is_a_mismatch(tmp_path):
    golden = tmp_path / "g.png"
    Image.new("RGB", (10, 10)).save(golden)
    result = compare_to_golden(str(golden), actual=Image.new("RGB", (12, 10)))
    assert result.matched is False and result.diff_pct == 100.0


def test_an_approval_extension_cannot_leave_the_folder(tmp_path):
    with pytest.raises(ValueError, match="extension"):
        verify_artifact("n", "evil", str(tmp_path / "approvals"), extension="x/../../outside/pwned")
    assert not (tmp_path / "outside").exists()


def test_zero_area_boxes_get_no_mark():
    class Element:
        def __init__(self, bounds):
            self.bounds, self.name, self.role = bounds, "e", "button"
    marks = mark_elements([Element((0, 0, 0, 0)), Element((10, 20, 30, 40))])
    assert [mark["bbox"] for mark in marks] == [[10, 20, 30, 40]]


def test_hashes_of_different_sizes_do_not_compare():
    with pytest.raises(ValueError):
        hamming_distance("ff" * 8, "ff" * 32)


def test_an_unknown_hash_algorithm_is_refused(tmp_path):
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    from je_auto_control.utils.executor.action_executor import _image_hash
    path = tmp_path / "i.png"
    Image.new("RGB", (8, 8)).save(path)
    with pytest.raises(AutoControlActionException, match="algo"):
        _image_hash(str(path), algo="phash")


def _item(name, bbox, role="ListItem"):
    return {"role": role, "name": name, "bbox": bbox}


def test_a_second_identical_row_appears():
    diff = diff_snapshots([_item("", [0, 0, 10, 10])],
                          [_item("", [0, 0, 10, 10]), _item("", [0, 10, 10, 10])])
    assert (len(diff["added"]), diff["moved"]) == (1, [])


def test_one_of_two_identical_buttons_vanishes():
    diff = diff_snapshots([_item("OK", [0, 0, 1, 1], "button"), _item("OK", [5, 5, 1, 1], "button")],
                          [_item("OK", [0, 0, 1, 1], "button")])
    assert (diff["removed"], diff["moved"]) == ([_item("OK", [5, 5, 1, 1], "button")], [])
