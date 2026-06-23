"""Headless tests for rotation/scale-tolerant matching on synthetic arrays."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from je_auto_control.utils.rotated_match import (  # noqa: E402
    match_rotated, match_rotated_all, scale_space,
)
from je_auto_control.utils.rotated_match.rotated_match import _rotate  # noqa: E402


def _template():
    # asymmetric (left half bright) so the best-correlating angle is unambiguous
    tmpl = np.zeros((24, 24), dtype=np.uint8)
    tmpl[:, :12] = 200
    return tmpl


def _haystack_with(patch, top, left):
    hay = np.zeros((140, 160), dtype=np.uint8)
    height, width = patch.shape[:2]
    hay[top:top + height, left:left + width] = patch
    return hay


def test_finds_rotated_template_and_recovers_angle():
    tmpl = _template()
    rotated = _rotate(tmpl, 30.0)
    hay = _haystack_with(rotated, top=50, left=40)
    best = match_rotated(tmpl, haystack=hay, angles=(0.0, 15.0, 30.0, 45.0),
                         min_score=0.9)
    assert best is not None
    assert abs(best.angle - 30.0) < 1e-9
    assert best.score >= 0.99
    assert abs(best.x - 40) <= 1 and abs(best.y - 50) <= 1


def test_zero_angle_locates_unrotated_patch():
    tmpl = _template()
    hay = _haystack_with(tmpl, top=20, left=30)
    best = match_rotated(tmpl, haystack=hay, angles=(0.0,), min_score=0.9)
    assert best is not None
    assert abs(best.angle) < 1e-9
    assert best.center == [30 + 12, 20 + 12]


def test_no_match_returns_none():
    tmpl = _template()
    hay = np.zeros((140, 160), dtype=np.uint8)  # template absent
    assert match_rotated(tmpl, haystack=hay, angles=(0.0, 30.0),
                         min_score=0.95) is None


def test_match_all_dedupes_overlaps():
    tmpl = _template()
    rotated = _rotate(tmpl, 30.0)
    hay = _haystack_with(rotated, top=50, left=40)
    # neighbouring angles overlap on the same spot; NMS collapses them to one
    hits = match_rotated_all(tmpl, haystack=hay, angles=(28.0, 30.0, 32.0),
                             min_score=0.85, nms_iou=0.3)
    assert len(hits) == 1
    assert abs(hits[0].angle - 30.0) < 1e-9


def test_scale_space_is_evenly_spaced_inclusive():
    scales = scale_space(0.8, 1.2, 3)
    assert len(scales) == 3
    assert abs(scales[0] - 0.8) < 1e-9
    assert abs(scales[1] - 1.0) < 1e-9
    assert abs(scales[2] - 1.2) < 1e-9


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_match_rotated" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_match_rotated" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_match_rotated" in specs


def test_facade_exports():
    assert hasattr(ac, "match_rotated") and "match_rotated" in ac.__all__
    assert hasattr(ac, "match_rotated_all")
