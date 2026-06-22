"""Headless tests for readability scoring. No Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.readability import (
    automated_readability_index, count_syllables, flesch_kincaid_grade,
    flesch_reading_ease, gunning_fog, readability_report, readability_stats,
    smog_index,
)

_EASY = "The cat sat on the mat. It was a sunny day."
_HARD = ("The utilisation of polysyllabic terminology substantially "
         "diminishes comprehensibility.")


def test_count_syllables_heuristic():
    assert count_syllables("cat") == 1
    assert count_syllables("apple") == 2          # silent-e drop keeps 2
    assert count_syllables("readability") == 5
    assert count_syllables("") == 0
    assert count_syllables("the") == 1            # min 1


def test_readability_stats_counts():
    stats = readability_stats(_EASY)
    assert stats["words"] == 11
    assert stats["sentences"] == 2
    assert stats["complex_words"] == 0


def test_easy_text_scores_higher_than_hard():
    assert flesch_reading_ease(_EASY) > flesch_reading_ease(_HARD)
    assert flesch_kincaid_grade(_EASY) < flesch_kincaid_grade(_HARD)
    assert gunning_fog(_EASY) < gunning_fog(_HARD)


def test_known_flesch_value():
    # deterministic formula output for the easy sample
    assert flesch_reading_ease(_EASY) == pytest.approx(108.96, abs=0.01)


def test_empty_text_is_zero():
    report = readability_report("")
    for key in ("flesch_reading_ease", "flesch_kincaid_grade", "gunning_fog",
                "smog_index", "automated_readability_index"):
        assert report[key] == pytest.approx(0.0)
    assert report["stats"]["words"] == 0


def test_report_contains_all_metrics():
    report = readability_report(_EASY)
    assert set(report) == {
        "flesch_reading_ease", "flesch_kincaid_grade", "gunning_fog",
        "smog_index", "automated_readability_index", "stats"}
    assert isinstance(smog_index(_EASY), float)
    assert isinstance(automated_readability_index(_EASY), float)


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([["AC_readability_report", {"text": _EASY}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["flesch_reading_ease"] == pytest.approx(108.96, abs=0.01)
    assert out["stats"]["words"] == 11


def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_readability_report" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_readability_report" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_readability_report" in specs


def test_facade_exports():
    for attr in ("count_syllables", "readability_stats", "flesch_reading_ease",
                 "flesch_kincaid_grade", "gunning_fog", "smog_index",
                 "automated_readability_index", "readability_report"):
        assert hasattr(ac, attr) and attr in ac.__all__
