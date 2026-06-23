"""Headless tests for SSIM structural comparison. No Qt."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.ssim import (   # noqa: E402
    ssim_changed_regions, ssim_compare,
)


def _base():
    """A textured 80x80 reference image (not flat — SSIM needs structure)."""
    yy, xx = np.mgrid[0:80, 0:80]
    return ((yy * 7 + xx * 11 + yy * xx) % 256).astype(np.uint8)


def _with_block():
    """The reference with a 20x20 block overwritten at (40, 30)."""
    changed = _base()
    changed[30:50, 40:60] = 0
    return changed


def test_identical_scores_one():
    base = _base()
    assert ssim_compare(base, base.copy()) == pytest.approx(1.0)


def test_change_lowers_score():
    assert ssim_compare(_base(), _with_block()) < 0.99


def test_ignore_region_restores_score():
    # masking out the changed block lifts the score back towards identical
    without = ssim_compare(_base(), _with_block())
    with_ignore = ssim_compare(_base(), _with_block(), ignore=[[40, 30, 20, 20]])
    assert with_ignore > without
    assert with_ignore > 0.98


def test_changed_regions_locates_the_block():
    regions = ssim_changed_regions(_base(), _with_block(), min_area=20)
    assert len(regions) == 1
    box = regions[0]
    # the changed blob overlaps the (40,30)-(60,50) block
    assert 30 <= box["x"] <= 50 and 20 <= box["y"] <= 40
    assert box["area"] >= 20


def test_changed_regions_empty_when_identical():
    base = _base()
    assert ssim_changed_regions(base, base.copy(), min_area=20) == []


def test_size_mismatch_raises():
    small = np.zeros((40, 40), dtype=np.uint8)
    with pytest.raises(ValueError):
        ssim_compare(_base(), small)


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_ssim_compare", "AC_ssim_changed_regions"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_ssim_compare", "ac_ssim_changed_regions"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_ssim_compare", "AC_ssim_changed_regions"} <= specs


def test_facade_exports():
    for attr in ("ssim_compare", "ssim_changed_regions"):
        assert hasattr(ac, attr) and attr in ac.__all__
