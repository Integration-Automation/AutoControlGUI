"""Verify image operations with OpenCV blocked and a NumPy/Pillow backend."""
import io
import sys

import numpy as np
from PIL import Image
import pytest

from je_auto_control.utils.cv2_utils import numpy_backend as backend, optional, template_detection
from je_auto_control.utils.exception.exceptions import AutoControlException


@pytest.fixture
def no_cv2(monkeypatch):
    monkeypatch.setitem(sys.modules, "cv2", None)


def test_fallback_selects_without_cv2(no_cv2):
    assert optional.require_image_backend() is backend
    with pytest.raises(AutoControlException) as error:
        optional.require_cv2()
    assert error.value.capability == "opencv"


def test_rgb_gray_and_bgr_match_opencv():
    cv2 = pytest.importorskip("cv2")
    rgb = np.random.default_rng(17).integers(0, 256, (35, 49, 3), dtype=np.uint8)
    np.testing.assert_array_equal(backend.cvtColor(rgb, backend.COLOR_RGB2GRAY), cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    np.testing.assert_array_equal(backend.cvtColor(rgb, backend.COLOR_RGB2BGR), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


@pytest.mark.parametrize("shape", [(23, 29), (19, 31), (540, 530)])
def test_normalized_scores_match_opencv_across_tile_edges(shape):
    cv2 = pytest.importorskip("cv2")
    image = np.random.default_rng(27).integers(0, 256, shape, dtype=np.uint8)
    template = image[-11:, -9:].copy()
    actual = backend.matchTemplate(image, template, backend.TM_CCOEFF_NORMED)
    expected = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    np.testing.assert_allclose(actual, expected, atol=1e-5)
    assert backend.minMaxLoc(actual)[-1] == (shape[1] - 9, shape[0] - 11)


def test_constant_templates_and_windows_are_finite():
    constant = np.full((8, 10), 127, dtype=np.uint8)
    varying = np.array([[0, 255], [127, 12]], dtype=np.uint8)
    np.testing.assert_array_equal(backend.matchTemplate(constant, constant[:2, :2], 5), np.ones((7, 9)))
    np.testing.assert_array_equal(backend.matchTemplate(constant, varying, 5), np.zeros((7, 9)))


def test_unicode_file_matching_and_origin_without_cv2(no_cv2, monkeypatch, tmp_path):
    rgb = np.random.default_rng(7).integers(0, 256, (65, 85, 3), dtype=np.uint8)
    frame = Image.fromarray(rgb)
    path = tmp_path / "\u6e2c\u8a66.png"
    frame.crop((20, 15, 31, 29)).save(path)
    monkeypatch.setattr(template_detection, "grab_logical", lambda *args, **kwargs: (frame.copy(), -100, -50))
    assert template_detection.find_image(path) == [True, [-80, -35, -69, -21]]
    found, boxes, drawn = template_detection.find_image_multi(path, draw_image=True)
    assert found and boxes == [[-80, -35, -69, -21]]
    assert drawn.shape == (65, 85)


def test_screenshot_keeps_bgr_array_contract(no_cv2, monkeypatch):
    from je_auto_control.wrapper import auto_control_screen

    rgb = np.array([[[1, 2, 3], [10, 20, 30]]], dtype=np.uint8)
    monkeypatch.setattr(auto_control_screen, "pil_screenshot", lambda **kwargs: Image.fromarray(rgb))
    result = auto_control_screen.screenshot()
    np.testing.assert_array_equal(result, rgb[:, :, ::-1])
    assert result.dtype == np.uint8


def test_unicode_image_file_round_trip_preserves_bgr(no_cv2, tmp_path):
    from je_auto_control.utils.cv2_utils.image_file import read_image, write_image

    bgr = np.random.default_rng(49).integers(0, 256, (13, 17, 3), dtype=np.uint8)
    path = tmp_path / "影像.png"
    write_image(path, bgr)
    np.testing.assert_array_equal(read_image(path, backend.IMREAD_COLOR), bgr)


def test_preview_accepts_readonly_grayscale_without_mutating_source(no_cv2, monkeypatch):
    image = np.random.default_rng(9).integers(0, 256, (23, 31), dtype=np.uint8)
    image.flags.writeable = False
    before = image.copy()
    monkeypatch.setattr(template_detection, "grab_logical", lambda *args, **kwargs: (image, 0, 0))
    found, box, preview = template_detection.find_image(image[5:11, 7:15], draw_image=True)
    assert found and box == [7, 5, 15, 11]
    assert preview.flags.writeable
    assert not np.array_equal(preview, before)
    np.testing.assert_array_equal(image, before)


def test_float32_normalized_matching_and_fft_budget(monkeypatch):
    image = np.random.default_rng(47).random((35, 41), dtype=np.float32)
    target = image[12:17, 16:23].copy()
    scores = backend.matchTemplate(image, target, backend.TM_CCOEFF_NORMED)
    assert scores.dtype == np.float32
    assert backend.minMaxLoc(scores)[-1] == (16, 12)
    monkeypatch.setattr(backend, "MAX_FFT_PIXELS", 8)
    with pytest.raises(backend.error, match="FFT budget"):
        backend.matchTemplate(image, target, backend.TM_CCOEFF_NORMED)


def test_fixed_frame_healing_reports_fallback_provenance(no_cv2, tmp_path):
    from je_auto_control.utils.self_healing.evaluation_models import EvaluationSample
    from je_auto_control.utils.self_healing.frame_strategies import TemplateFrameStrategy

    rgb = np.random.default_rng(21).integers(0, 256, (31, 41, 3), dtype=np.uint8)
    frame = Image.fromarray(rgb)
    path = tmp_path / "template.png"
    frame.crop((7, 5, 15, 11)).save(path)
    output = io.BytesIO()
    frame.save(output, format="PNG")
    result = TemplateFrameStrategy(str(path)).locate(EvaluationSample(output.getvalue()))
    assert result.coordinates == (11, 8)
    assert result.backend == "numpy-pillow"


def test_missing_both_backends_is_typed(no_cv2, monkeypatch):
    monkeypatch.setitem(sys.modules, "je_auto_control.utils.cv2_utils.numpy_backend", None)
    with pytest.raises(AutoControlException) as error:
        optional.require_image_backend()
    assert error.value.capability == "image_matching"
    assert error.value.state == "needs_dependency"


def test_unsupported_method_and_resource_budget_are_typed(monkeypatch):
    image = np.zeros((30, 40), dtype=np.uint8)
    with pytest.raises(backend.error):
        backend.matchTemplate(image, image[:3, :4], 0)
    monkeypatch.setattr(backend, "MAX_FRAME_PIXELS", 100)
    with pytest.raises(backend.error, match="budget"):
        backend.matchTemplate(image, image[:3, :4], 5)
