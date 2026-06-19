"""Headless tests for fuzzy matching/dedupe. The difflib backend is always
present, so these run with no extra dependency; assertions check ordering and
thresholds, not exact backend-specific float values. Pure stdlib, no Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.fuzzy import (
    BACKEND, fuzzy_best_match, fuzzy_dedupe, fuzzy_matches, fuzzy_ratio)


def test_backend_is_known():
    assert BACKEND in ("difflib", "rapidfuzz")


def test_ratio_bounds_and_identity():
    assert fuzzy_ratio("hello", "hello") == pytest.approx(1.0)
    assert fuzzy_ratio("hello", "xxxxx") < 0.5
    assert 0.0 <= fuzzy_ratio("Save", "save", ignore_case=False) <= 1.0


def test_ratio_ignore_case():
    assert fuzzy_ratio("SAVE", "save", ignore_case=True) == pytest.approx(1.0)
    assert fuzzy_ratio("SAVE", "save", ignore_case=False) < 1.0


def test_best_match_picks_closest():
    choices = ["Cancel", "Save As...", "Save", "Submit"]
    match, score, index = fuzzy_best_match("Sve", choices)
    assert match == "Save"
    assert choices[index] == "Save"
    assert score > 0.5


def test_best_match_cutoff_returns_none():
    assert fuzzy_best_match("zzzzz", ["alpha", "beta"],
                            score_cutoff=0.8) is None


def test_matches_sorted_and_limited():
    choices = ["login", "logon", "logout", "register"]
    ranked = fuzzy_matches("login", choices, limit=2)
    assert len(ranked) == 2
    scores = [score for _, score, _ in ranked]
    assert scores == sorted(scores, reverse=True)
    assert ranked[0][0] == "login"


def test_dedupe_collapses_near_duplicates():
    items = ["Invoice", "invoice ", "Receipt", "INVOICE"]
    unique = fuzzy_dedupe(items, threshold=0.85)
    assert "Invoice" in unique
    assert "Receipt" in unique
    assert len(unique) == 2          # the invoice variants collapse


def test_dedupe_keeps_distinct():
    items = ["apple", "banana", "cherry"]
    assert fuzzy_dedupe(items) == items


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_fuzzy_best_match",
        {"query": "Sumbit", "choices": ["Cancel", "Submit", "Save"]},
    ]])
    result = next(v for v in rec.values() if isinstance(v, dict))
    assert result["match"] == "Submit"

    rec2 = ac.execute_action([[
        "AC_fuzzy_dedupe",
        {"items": ["a", "a", "b"], "threshold": 0.95},
    ]])
    deduped = next(v for v in rec2.values() if isinstance(v, dict))
    assert deduped["unique"] == ["a", "b"]


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_fuzzy_ratio", "AC_fuzzy_best_match",
            "AC_fuzzy_dedupe"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_fuzzy_ratio", "ac_fuzzy_best_match",
            "ac_fuzzy_dedupe"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_fuzzy_ratio", "AC_fuzzy_best_match",
            "AC_fuzzy_dedupe"} <= cmds


def test_facade_exports():
    for attr in ("fuzzy_ratio", "fuzzy_best_match", "fuzzy_matches",
                 "fuzzy_dedupe"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
