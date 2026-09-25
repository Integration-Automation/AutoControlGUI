"""Image helpers follow their references at the edges (synthetic images only).

pixelmatch's anti-aliasing test instead of a morphological open; L1-normalised
histograms with a symmetric intersection; SSIM with the images' dynamic range
(Wang et al. 2004); the true median line height; no IoU-zero matches; arrays
in the perceptual hashes.
"""
import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.element_diff.element_diff import (  # noqa: E402
    assign_stable_ids, match_elements,
)
from je_auto_control.utils.heading_segment.heading_segment import classify_lines  # noqa: E402
from je_auto_control.utils.image_dedup.perceptual_hash import average_hash, dhash  # noqa: E402
from je_auto_control.utils.img_histogram.img_histogram import (  # noqa: E402
    compare_histograms, histogram_changed, image_histogram,
)
from je_auto_control.utils.perceptual_diff import perceptual_diff  # noqa: E402
from je_auto_control.utils.ssim.ssim import ssim_compare  # noqa: E402


def _label(text):
    image = np.full((40, 200, 3), 255, np.uint8)
    # Hinted 1 px strokes (no anti-aliasing): the morphological open erased all of them.
    cv2.putText(image, text, (5, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_8)
    return image


def test_edited_small_text_is_a_perceptual_change():
    assert perceptual_diff(_label("Total: 1200"), _label("Total: 1780")).diff_pixels > 0
    assert perceptual_diff(_label("Total: 1200"), _label("Total: 1200")).diff_pixels == 0


def _solid(rgb, shape=(40, 40)):
    return np.full(shape + (3,), rgb, np.uint8)


def test_histogram_intersection_is_symmetric_and_not_containment():
    red = _solid((255, 0, 0))
    half = red.copy()
    half[:, 20:] = (0, 0, 255)
    forward = compare_histograms(image_histogram(red), image_histogram(half), method="intersection")
    backward = compare_histograms(image_histogram(half), image_histogram(red), method="intersection")
    assert forward == backward < 1.0
    assert histogram_changed(red, half, method="intersection")


def test_a_flat_histogram_does_not_correlate_with_a_spike():
    ramp = np.tile(np.arange(256, dtype=np.uint8), (8, 1))
    ramp = np.dstack([ramp] * 3)
    black = np.zeros_like(ramp)
    assert histogram_changed(ramp, black, space="gray")
    assert not histogram_changed(ramp, ramp.copy(), space="gray")


def test_ssim_uses_the_images_dynamic_range():
    rng = np.random.default_rng(3)
    a = rng.integers(0, 256, (64, 64)).astype(np.uint8)
    b = rng.integers(0, 256, (64, 64)).astype(np.uint8)
    as_bytes = ssim_compare(a, b)
    as_floats = ssim_compare(a / 255.0, b / 255.0)
    assert as_floats == pytest.approx(as_bytes, abs=0.01)
    assert as_bytes < 0.2


def test_ssim_takes_a_single_channel_array():
    frame = np.zeros((16, 16, 1), np.uint8)
    assert ssim_compare(frame, frame.copy()) == 1.0


def test_the_median_of_an_even_count_is_the_mean_of_the_middle_two():
    lines = [{"x": 0, "y": 0, "width": 100, "height": 30, "text": "Title"},
             {"x": 0, "y": 40, "width": 100, "height": 15, "text": "body"}]
    roles = [line["role"] for line in classify_lines(lines)]
    assert roles == ["heading", "body"]


def test_boxes_that_do_not_overlap_never_match():
    near = {"x": 0, "y": 0, "width": 10, "height": 10}
    far = [{"x": 100, "y": 100, "width": 10, "height": 10},
           {"x": 200, "y": 200, "width": 10, "height": 10}]
    result = match_elements([near], far, iou_threshold=0)
    assert result["matched"] == [] and result["removed"] == [near]
    carried = assign_stable_ids([dict(far[0])], [dict(near, id=7)], iou_threshold=0)
    assert carried[0]["id"] != 7


def test_the_perceptual_hashes_accept_arrays():
    image = np.zeros((32, 32, 3), np.uint8)
    image[:, 16:] = 255
    from PIL import Image
    assert average_hash(image) == average_hash(Image.fromarray(image))
    assert dhash(image) == dhash(Image.fromarray(image))
