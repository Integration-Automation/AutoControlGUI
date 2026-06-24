"""Headless tests for per-run step timeline (waterfall + bottleneck steps)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.step_timeline import build_timeline, critical_steps


def _sequential():
    return [{"name": "login", "duration": 1.0},
            {"name": "load", "duration": 4.0},
            {"name": "submit", "duration": 1.0}]


def test_sequential_waterfall_offsets_and_bottleneck():
    tl = build_timeline(_sequential())
    offsets = {s["name"]: s["offset"] for s in tl["steps"]}
    assert offsets == {"login": 0.0, "load": 1.0, "submit": 5.0}
    assert tl["total"] == pytest.approx(6.0)
    assert tl["busy"] == pytest.approx(6.0)
    assert tl["parallelism"] == pytest.approx(1.0)        # purely sequential
    assert tl["bottleneck"] == {"name": "load", "duration": 4.0}


def test_pct_share_of_total():
    pct = {s["name"]: s["pct"] for s in build_timeline(_sequential())["steps"]}
    assert pct["load"] == pytest.approx(66.7, abs=0.1)


def test_overlapping_run_reports_parallelism():
    par = [{"name": "a", "start": 0.0, "duration": 3.0},
           {"name": "b", "start": 1.0, "duration": 3.0}]
    tl = build_timeline(par)
    assert tl["total"] == pytest.approx(4.0)              # span 0..4
    assert tl["busy"] == pytest.approx(6.0)               # 3 + 3
    assert tl["parallelism"] == pytest.approx(1.5)        # overlap detected


def test_critical_steps_ranked_with_pct():
    crit = critical_steps(_sequential(), top=2)
    assert [s["name"] for s in crit] == ["load", "login"]   # longest first
    assert crit[0]["pct"] == pytest.approx(66.7, abs=0.1)
    assert len(critical_steps(_sequential(), top=1)) == 1


def test_empty_run():
    assert build_timeline([]) == {"steps": [], "total": 0.0, "busy": 0.0,
                                  "bottleneck": None, "parallelism": 0.0}
    assert critical_steps([]) == []


# --- wiring ---------------------------------------------------------------

def test_executor_paths():
    import json
    from je_auto_control.utils.executor.action_executor import (
        _build_timeline, _critical_steps)
    steps_json = json.dumps(_sequential())
    assert _build_timeline(steps_json)["bottleneck"]["name"] == "load"
    assert _critical_steps(steps_json, top=1)["steps"][0]["name"] == "load"


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_build_timeline", "AC_critical_steps"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_build_timeline", "ac_critical_steps"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_build_timeline", "AC_critical_steps"} <= specs


def test_facade_exports():
    for name in ("build_timeline", "critical_steps"):
        assert hasattr(ac, name) and name in ac.__all__
