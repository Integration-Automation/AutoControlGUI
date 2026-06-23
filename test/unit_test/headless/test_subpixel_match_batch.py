"""Headless tests for sub-pixel template-match refinement."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.subpixel_match import (  # noqa: E402
    match_subpixel, refine_peak,
)


def _template():
    tmpl = np.zeros((24, 24), dtype=np.uint8)
    tmpl[:, :12] = 200
    return tmpl


def _haystack(top, left):
    hay = np.zeros((120, 160), dtype=np.uint8)
    hay[top:top + 24, left:left + 24] = _template()
    return hay


def test_refine_peak_symmetric_is_zero():
    smap = np.array([[0.0, 0.0, 0.0],
                     [0.0, 1.0, 0.0],
                     [0.0, 0.0, 0.0]], dtype=np.float32)
    offset_x, offset_y = refine_peak(smap, (1, 1))
    assert abs(offset_x) < 1e-9 and abs(offset_y) < 1e-9


def test_refine_peak_biased_offset_sign():
    # right neighbour higher than left → peak nudged toward +x
    row = np.array([[0.2, 1.0, 0.6]], dtype=np.float32)
    offset_x, offset_y = refine_peak(row, (1, 0))
    assert offset_x > 0.0 and abs(offset_y) < 1e-9


def test_match_subpixel_locates_and_centres():
    match = match_subpixel(_template(), haystack=_haystack(20, 30), min_score=0.8)
    assert match is not None
    assert match.x == 30 and match.y == 20
    # exact alignment → offset ~0, cx ≈ integer centre
    assert abs(match.cx - (30 + 12)) < 0.6
    assert abs(match.cy - (20 + 12)) < 0.6


def test_match_subpixel_min_score_filters():
    blank = np.zeros((120, 160), dtype=np.uint8)
    assert match_subpixel(_template(), haystack=blank, min_score=0.95) is None


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_match_subpixel" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_match_subpixel" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_match_subpixel" in specs


def test_facade_exports():
    for name in ("match_subpixel", "refine_peak", "SubPixelMatch"):
        assert hasattr(ac, name) and name in ac.__all__
