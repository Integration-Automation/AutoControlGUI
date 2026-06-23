"""Headless tests for perceptual (YIQ) image diff. No Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlActionException

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.perceptual_diff import (   # noqa: E402
    PerceptualDiffResult, assert_perceptual, perceptual_diff,
)


def _base():
    return np.full((100, 120, 3), 128, dtype=np.uint8)


def _block():
    img = _base()
    img[30:60, 40:80] = (255, 0, 0)      # 40x30 solid change
    return img


def test_identical_has_no_diff():
    result = perceptual_diff(_base(), _base().copy())
    assert result.diff_pixels == 0 and result.diff_ratio == pytest.approx(0.0)


def test_solid_block_is_counted():
    result = perceptual_diff(_base(), _block())
    assert isinstance(result, PerceptualDiffResult)
    assert result.diff_pixels == 1200 and len(result.regions) == 1
    assert result.diff_ratio == pytest.approx(0.1)


def test_thin_fringe_suppressed_as_antialiasing():
    fringe = _base()
    fringe[:, 60:61] = (200, 200, 200)   # 1px-wide vertical edge difference
    assert perceptual_diff(_base(), fringe, include_aa=False).diff_pixels == 0
    assert perceptual_diff(_base(), fringe, include_aa=True).diff_pixels == 100


def test_threshold_tolerates_small_colour_shift():
    shifted = _base().copy()
    shifted[:, :] = (132, 132, 132)      # small uniform shift
    assert perceptual_diff(_base(), shifted, threshold=0.2).diff_pixels == 0


def test_size_mismatch_raises():
    with pytest.raises(ValueError):
        perceptual_diff(_base(), np.zeros((10, 10, 3), dtype=np.uint8))


def test_assert_perceptual_raises_over_budget():
    with pytest.raises(AutoControlActionException):
        assert_perceptual(_base(), _block(), max_diff_ratio=0.0)
    assert assert_perceptual(_base(), _base().copy()).diff_pixels == 0


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_perceptual_diff" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_perceptual_diff" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_perceptual_diff" in specs


def test_facade_exports():
    for attr in ("perceptual_diff", "assert_perceptual", "PerceptualDiffResult"):
        assert hasattr(ac, attr) and attr in ac.__all__
