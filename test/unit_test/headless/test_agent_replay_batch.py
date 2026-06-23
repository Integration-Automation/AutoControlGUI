"""Headless tests for the agent-trajectory trace. No Qt; runner is injected."""
import je_auto_control as ac
from je_auto_control.utils.agent_replay import (
    from_jsonl, record_step, replay_trace, to_jsonl,
)


def _trace():
    trace = []
    record_step(trace, "obs0", ["AC_click_mouse", {"x": 1, "y": 2}])
    record_step(trace, "obs1", ["AC_write", {"write_string": "hi"}],
                result={"ok": True})
    return trace


def test_record_step_indexes_and_keeps_result():
    trace = _trace()
    assert [s["step"] for s in trace] == [0, 1]
    assert trace[0]["observation"] == "obs0"
    assert "result" not in trace[0] and trace[1]["result"] == {"ok": True}


def test_jsonl_round_trip():
    trace = _trace()
    text = to_jsonl(trace)
    assert len(text.splitlines()) == 2
    assert from_jsonl(text) == trace


def test_from_jsonl_skips_blank_lines():
    assert from_jsonl('{"step": 0}\n\n  \n{"step": 1}\n') == [{"step": 0},
                                                             {"step": 1}]


def test_replay_runs_each_action_in_order():
    calls = []
    results = replay_trace(_trace(), lambda action: calls.append(action[0])
                           or f"ran:{action[0]}")
    assert calls == ["AC_click_mouse", "AC_write"]
    assert [(r["step"], r["result"]) for r in results] == [
        (0, "ran:AC_click_mouse"), (1, "ran:AC_write")]


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_replay_trace" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_replay_trace" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_replay_trace" in specs


def test_facade_exports():
    for attr in ("record_step", "to_jsonl", "from_jsonl", "replay_trace"):
        assert hasattr(ac, attr) and attr in ac.__all__
