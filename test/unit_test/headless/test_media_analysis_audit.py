"""Media / analysis defects from the 2026-09-24 audit (synthetic data only).

Float bucket edges put points in the previous bucket; the KS series had not
converged for small lambda and called identical samples drifted; histogram
intersection was unnormalised; an unreadable video measured 0 motion; a
negative ignore box ignored nothing; masked pixels diluted the visual-diff
percentage; grayscale arrays compared by their first column; a PIL frame or
a Path broke the video report loader; pypdf's DependencyError escaped.
"""
import numpy as np
import pytest
from PIL import Image

from je_auto_control.utils.color_region.color_region import _to_rgb
from je_auto_control.utils.data_drift.data_drift import ks_two_sample
from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.img_histogram.img_histogram import compare_histograms
from je_auto_control.utils.media_assert import media
from je_auto_control.utils.pdf import pdf_reader
from je_auto_control.utils.ssim.ssim import _keep_mask
from je_auto_control.utils.timeseries.timeseries import ts_downsample, ts_resample
from je_auto_control.utils.video_report.video_report import _default_loader
from je_auto_control.utils.visual_regression.compare import MaskRegion, image_difference


def test_points_on_a_float_bucket_edge_land_in_that_bucket():
    series = [(0.0, 1.0), (0.3, 2.0), (0.6, 3.0)]
    assert [start for start, _v in ts_downsample(series, 0.1)] == [0.0, 0.3, 0.6]
    assert ts_resample(series, 0.3) == [(0.0, 1.0), (0.3, 2.0), (0.6, 3.0)]


def test_identical_large_samples_are_not_drifted():
    sample = list(np.linspace(0, 1, 5000))
    shifted = [value + 1e-6 for value in sample]   # one step apart: a tiny, non-zero lambda
    assert ks_two_sample(sample, shifted)["p_value"] > 0.99


def test_histogram_intersection_is_normalised():
    red, blue = [0.0, 3.0, 0.0], [3.0, 0.0, 0.0]
    assert compare_histograms(red, blue, method="intersection") == 0.0
    assert compare_histograms(red, red, method="intersection") == 1.0


def test_an_unreadable_video_is_an_error_not_zero_motion(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")
    with pytest.raises(ValueError):
        media.video_segment_motion(str(broken))


def test_a_negative_ignore_box_still_ignores_its_visible_part():
    keep = _keep_mask((10, 10), [(-5, 0, 10, 10)])
    assert not keep[:, :5].any() and keep[:, 5:].all()


def test_masked_pixels_do_not_dilute_the_difference():
    expected = Image.new("RGB", (10, 10), (0, 0, 0))
    actual = Image.new("RGB", (10, 10), (255, 255, 255))
    differing, total, _overlay = image_difference(
        actual, expected, masks=[MaskRegion(0, 0, 8, 9)])
    assert total == 10 * 10 - 9 * 10 and differing == total


def test_grayscale_arrays_are_compared_as_images():
    gray = np.zeros((4, 4), np.uint8)
    gray[2, 3] = 255
    rgb = _to_rgb(gray)
    assert rgb.shape == (4, 4, 3) and rgb[2, 3].tolist() == [255, 255, 255]


def test_the_video_report_loader_takes_paths_and_pil_frames(tmp_path):
    import cv2
    path = tmp_path / "frame.png"
    cv2.imwrite(str(path), np.full((2, 2, 3), (255, 0, 0), np.uint8))
    assert _default_loader(path)[0, 0].tolist() == [255, 0, 0]
    frame = _default_loader(Image.new("RGB", (2, 2), (255, 0, 0)))
    assert frame[0, 0].tolist() == [0, 0, 255]  # RGB red in BGR order


def test_a_pdf_dependency_error_is_an_action_error(monkeypatch, tmp_path):
    errors = pytest.importorskip("pypdf.errors")

    def fail(_path, pages=None):
        raise errors.DependencyError("cryptography is required for AES")

    wrapped = pdf_reader._pdf_errors_as_action_errors(fail)
    with pytest.raises(AutoControlActionException):
        wrapped(str(tmp_path / "x.pdf"))
