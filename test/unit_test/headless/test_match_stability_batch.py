"""Headless tests for pre-match settle gating + match persistence."""
import pytest

import je_auto_control as ac

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from je_auto_control.utils.match_stability import (  # noqa: E402
    match_persistence, region_stability,
)


def _frame(extra=None):
    img = np.zeros((120, 160), dtype=np.uint8)
    cv2.rectangle(img, (30, 30), (90, 80), 255, 2)   # stable content
    if extra is not None:
        cv2.circle(img, extra, 8, 200, -1)           # moving element
    return img


def _template():
    tmpl = np.zeros((24, 24), dtype=np.uint8)
    tmpl[:, :12] = 200
    return tmpl


def _haystack(left):
    hay = np.zeros((120, 160), dtype=np.uint8)
    hay[40:64, left:left + 24] = _template()
    return hay


def test_identical_frames_are_stable():
    frames = [_frame(), _frame(), _frame()]
    result = region_stability(frames, settle_threshold=0.99)
    assert result["stable"] is True
    assert result["min_ssim"] >= 0.99


def test_moving_element_is_unstable():
    frames = [_frame((10, 10)), _frame((60, 60)), _frame((110, 100))]
    result = region_stability(frames, settle_threshold=0.99)
    assert result["stable"] is False
    assert result["min_ssim"] < 0.99


def test_single_frame_is_trivially_stable():
    assert region_stability([_frame()])["stable"] is True


def test_match_persists_across_frames():
    frames = [_haystack(50), _haystack(51), _haystack(50)]   # ~steady
    result = match_persistence(_template(), frames, min_score=0.8, agree_px=8)
    assert result["persisted"] is True
    assert result["n_hits"] == 3


def test_match_not_persistent_when_missing():
    frames = [_haystack(50), np.zeros((120, 160), np.uint8), _haystack(50)]
    result = match_persistence(_template(), frames, min_score=0.8)
    assert result["persisted"] is False
    assert result["n_hits"] == 2


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_region_stability", "AC_match_persistence"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_region_stability", "ac_match_persistence"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_region_stability", "AC_match_persistence"} <= specs


def test_facade_exports():
    for name in ("region_stability", "match_persistence"):
        assert hasattr(ac, name) and name in ac.__all__
