"""Headless tests for weighted candidate scoring. No Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.element_scoring import (
    ScoredCandidate, best_candidate, score_candidates,
)


def _candidates():
    return [
        {"role": "button", "name": "Save", "x": 10, "y": 10, "width": 40,
         "height": 20, "enabled": True},
        {"role": "button", "name": "Save As", "x": 100, "y": 10, "width": 60,
         "height": 20, "enabled": True},
        {"role": "link", "name": "Save", "x": 10, "y": 200, "width": 40,
         "height": 20, "enabled": False},
    ]


def test_exact_button_near_anchor_ranks_first():
    ranked = score_candidates(_candidates(), want_role="button", want_name="Save",
                              anchor=(20, 15))
    assert ranked[0].element["name"] == "Save"
    assert ranked[0].element["role"] == "button"
    assert ranked[0].score > ranked[1].score > ranked[2].score


def test_matched_on_breakdown():
    top = score_candidates(_candidates(), want_role="button",
                           want_name="Save")[0]
    assert top.matched_on["role"] == pytest.approx(1.0)
    assert top.matched_on["name"] == pytest.approx(1.0)
    assert top.matched_on["enabled"] == pytest.approx(1.0)


def test_disabled_wrong_role_ranks_last():
    ranked = score_candidates(_candidates(), want_role="button", want_name="Save")
    assert ranked[-1].element["role"] == "link"      # disabled + wrong role


def test_injected_similarity_is_used():
    calls = []

    def sim(a, b):
        calls.append((a, b))
        return 1.0 if a == b else 0.0

    score_candidates(_candidates(), want_name="Save", name_similarity=sim,
                     prefer_enabled=False)
    assert calls and all(call[0] == "Save" for call in calls)


def test_best_candidate_and_empty():
    assert best_candidate(_candidates(), want_name="Save").element["name"] == "Save"
    assert best_candidate([], want_name="x") is None


def test_scored_candidate_to_dict():
    top = score_candidates(_candidates(), want_role="button")[0]
    assert isinstance(top, ScoredCandidate)
    assert set(top.to_dict()) == {"element", "score", "matched_on"}


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_score_candidates", "AC_best_candidate"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_score_candidates", "ac_best_candidate"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_score_candidates", "AC_best_candidate"} <= specs


def test_facade_exports():
    for attr in ("score_candidates", "best_candidate", "ScoredCandidate"):
        assert hasattr(ac, attr) and attr in ac.__all__
