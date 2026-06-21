"""Headless tests for string-distance metrics. Pure stdlib, no Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.text_similarity import (
    damerau_levenshtein, dice, jaccard, jaro, jaro_winkler, levenshtein,
    similarity,
)


def test_levenshtein():
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("abc", "abc") == 0
    assert levenshtein("", "abc") == 3


def test_damerau_handles_transposition():
    assert levenshtein("ab", "ba") == 2          # two substitutions
    assert damerau_levenshtein("ab", "ba") == 1  # one transposition


def test_jaro_and_winkler():
    assert jaro("MARTHA", "MARHTA") == pytest.approx(0.9444, abs=1e-3)
    jw = jaro_winkler("MARTHA", "MARHTA")
    assert jw == pytest.approx(0.9611, abs=1e-3)
    assert jaro_winkler("abc", "abc") == pytest.approx(1.0)
    # common prefix boosts winkler above plain jaro
    assert jaro_winkler("prefix", "preXXX") >= jaro("prefix", "preXXX")


def test_jaccard_and_dice():
    assert jaccard("night", "night") == pytest.approx(1.0)
    assert jaccard("abc", "xyz") == pytest.approx(0.0)
    assert dice("night", "nacht", n=2) == pytest.approx(0.25)
    assert jaccard("", "") == pytest.approx(1.0)


def test_similarity_normalises_edit_distance():
    # levenshtein("kitten","sitting")=3, max_len=7 -> 1 - 3/7
    assert similarity("kitten", "sitting", metric="levenshtein") == \
        pytest.approx(1 - 3 / 7)
    assert similarity("abc", "abc", metric="levenshtein") == pytest.approx(1.0)
    assert similarity("a", "b", metric="jaro_winkler") == pytest.approx(0.0)


def test_similarity_unknown_metric():
    with pytest.raises(ValueError):
        similarity("a", "b", metric="nope")


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_text_similarity",
        {"a": "login", "b": "lgoin", "metric": "damerau_levenshtein"}]])
    score = next(v for v in rec.values() if isinstance(v, dict))["score"]
    assert score == pytest.approx(1 - 1 / 5)     # one transposition over len 5


def test_wiring():
    assert "AC_text_similarity" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_text_similarity" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_text_similarity" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("levenshtein", "damerau_levenshtein", "jaro", "jaro_winkler",
                 "jaccard", "dice", "similarity"):
        assert hasattr(ac, attr) and attr in ac.__all__
