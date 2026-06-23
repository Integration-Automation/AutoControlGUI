"""Headless tests for multi-template consensus matching."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.match_ensemble import match_ensemble, vote_centers


def test_vote_centers_majority_agrees():
    # three references agree near (100,100); one outlier
    result = vote_centers([[100, 100], [102, 98], [97, 103], [400, 400]],
                          agree_px=10, min_votes=2)
    assert result is not None
    assert abs(result["point"][0] - 99) <= 4
    assert result["votes"] == 3 and result["n_candidates"] == 4


def test_vote_centers_too_few_votes_is_none():
    assert vote_centers([[0, 0], [500, 500]], agree_px=10, min_votes=2) is None


def test_vote_centers_empty():
    assert vote_centers([], min_votes=1) is None


def test_match_ensemble_with_injected_haystack():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    tmpl = np.zeros((24, 24), dtype=np.uint8)
    tmpl[:, :12] = 200
    hay = np.zeros((120, 160), dtype=np.uint8)
    hay[40:64, 50:74] = tmpl
    # three reference crops (here identical) all land on the same spot
    result = match_ensemble([tmpl, tmpl, tmpl], haystack=hay, min_score=0.8,
                            agree_px=8, min_votes=2)
    assert result is not None
    assert result["votes"] == 3
    assert abs(result["point"][0] - 62) <= 2   # centre of the 24px patch at x=50


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_match_ensemble", "AC_vote_centers"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_match_ensemble", "ac_vote_centers"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_match_ensemble", "AC_vote_centers"} <= specs


def test_facade_exports():
    for name in ("match_ensemble", "vote_centers"):
        assert hasattr(ac, name) and name in ac.__all__
