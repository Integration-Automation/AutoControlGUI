"""Headless tests for OCR/match image preprocessing. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.preprocess import (   # noqa: E402
    binarize, denoise, deskew, detect_skew_angle, enhance_contrast,
    preprocess_image, to_grayscale, upscale,
)


def _color():
    img = np.zeros((40, 60, 3), dtype=np.uint8)
    img[:, :30] = (80, 80, 80)
    img[:, 30:] = (200, 200, 200)
    return img


def _skewed(angle):
    """A dark horizontal bar on a light background, rotated by ``angle`` degrees."""
    canvas = np.full((120, 200), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (40, 55), (160, 65), 0, -1)
    matrix = cv2.getRotationMatrix2D((100, 60), angle, 1.0)
    return cv2.warpAffine(canvas, matrix, (200, 120), borderValue=255)


def test_grayscale_drops_channels():
    assert to_grayscale(_color()).shape == (40, 60)


def test_upscale_doubles_dimensions():
    assert upscale(_color(), scale=2.0).shape[:2] == (80, 120)


def test_upscale_rejects_unknown_interp():
    with pytest.raises(ValueError):
        upscale(_color(), interp="magic")


def test_binarize_otsu_is_two_valued():
    assert sorted(set(binarize(_color()).flatten().tolist())) == [0, 255]


def test_binarize_adaptive_keeps_shape():
    assert binarize(_color(), method="adaptive_gaussian").shape == (40, 60)


def test_binarize_rejects_unknown_method():
    with pytest.raises(ValueError):
        binarize(_color(), method="triangle")


def test_denoise_and_contrast_keep_grayscale_shape():
    assert denoise(_color()).shape == (40, 60)
    assert enhance_contrast(_color()).shape == (40, 60)


def test_detect_skew_recovers_angle_magnitude():
    assert 5.0 <= abs(detect_skew_angle(_skewed(10))) <= 15.0


def test_detect_skew_clamps_to_zero_beyond_max():
    assert detect_skew_angle(_skewed(10), max_angle=3.0) == 0.0


def test_deskew_reduces_skew():
    rotated = _skewed(10)
    before = abs(detect_skew_angle(rotated))
    after = abs(detect_skew_angle(deskew(rotated)))
    assert after < before


def test_pipeline_chains_steps():
    out = preprocess_image(_color(), steps=("grayscale", "upscale", "binarize"))
    assert out.ndim == 2 and out.shape == (80, 120)
    assert sorted(set(out.flatten().tolist())) == [0, 255]


def test_pipeline_rejects_unknown_step():
    with pytest.raises(ValueError):
        preprocess_image(_color(), steps=("sharpen",))


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_preprocess_image" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_preprocess_image" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_preprocess_image" in specs


def test_facade_exports():
    for attr in ("preprocess_image", "to_grayscale", "binarize", "upscale",
                 "deskew", "enhance_contrast"):
        assert hasattr(ac, attr) and attr in ac.__all__


def test_executor_writes_output(tmp_path):
    from je_auto_control.utils.executor.action_executor import _preprocess_image
    src = tmp_path / "src.png"
    cv2.imwrite(str(src), _color())
    out = tmp_path / "out.png"
    result = _preprocess_image(str(out), source=str(src),
                               steps=["grayscale", "binarize"])
    assert result["path"] == str(out) and out.exists()
    assert result["width"] == 60 and result["height"] == 40
