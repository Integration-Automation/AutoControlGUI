"""Headless tests for run-trace diffing (LCS-aligned step diff)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.run_diff import diff_runs, summarize_run_diff


def _before():
    return [
        {"name": "login", "status": "ok", "duration": 1.0},
        {"name": "open_form", "status": "ok", "duration": 2.0},
        {"name": "submit", "status": "ok", "duration": 1.0},
    ]


def _after():
    return [
        {"name": "login", "status": "ok", "duration": 1.1},
        {"name": "accept_cookies", "status": "ok", "duration": 0.5},   # inserted
        {"name": "open_form", "status": "ok", "duration": 5.0},        # 2.5x slower
        {"name": "submit", "status": "error", "duration": 1.0,
         "error": r"Timeout at C:\app.py line 42 (0x7ff)"},           # flip
    ]


def test_lcs_alignment_isolates_the_insert():
    diff = diff_runs(_before(), _after())
    # the inserted step is the only add; login/open_form/submit stay aligned
    assert [s["name"] for s in diff["added"]] == ["accept_cookies"]
    assert diff["removed"] == []
    assert diff["aligned"] == 3
    assert diff["identical"] is False


def test_status_flip_carries_failure_signature():
    flips = diff_runs(_before(), _after())["status_flips"]
    assert len(flips) == 1
    assert flips[0]["name"] == "submit"
    assert flips[0]["from"] == "ok" and flips[0]["to"] == "error"
    assert len(flips[0]["signature"]) == 12       # failure_signature attached


def test_timing_regression_detected_with_ratio():
    regs = diff_runs(_before(), _after())["timing_regressions"]
    assert len(regs) == 1 and regs[0]["name"] == "open_form"
    assert regs[0]["ratio"] == pytest.approx(2.5)
    # a small slowdown under the factor is not a regression
    slow = diff_runs([{"name": "a", "duration": 1.0}],
                     [{"name": "a", "duration": 1.2}])
    assert slow["timing_regressions"] == []


def test_removed_step_detected():
    diff = diff_runs(_before(), [_before()[0], _before()[2]])  # drop open_form
    assert [s["name"] for s in diff["removed"]] == ["open_form"]
    assert diff["added"] == []


def test_identical_runs():
    diff = diff_runs(_before(), _before())
    assert diff["identical"] is True
    assert summarize_run_diff(diff) == "no change"


def test_summary_lists_changes():
    summary = summarize_run_diff(diff_runs(_before(), _after()))
    assert "added" in summary and "flip" in summary and "regression" in summary


# --- wiring ---------------------------------------------------------------

def test_executor_path_includes_summary():
    import json
    from je_auto_control.utils.executor.action_executor import _diff_runs
    out = _diff_runs(json.dumps(_before()), json.dumps(_after()))
    assert out["aligned"] == 3
    assert out["summary"] == summarize_run_diff(diff_runs(_before(), _after()))


def test_wiring():
    known = set(ac.executor.known_commands())
    assert "AC_diff_runs" in known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_diff_runs" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_diff_runs" in specs


def test_facade_exports():
    for name in ("diff_runs", "summarize_run_diff"):
        assert hasattr(ac, name) and name in ac.__all__
