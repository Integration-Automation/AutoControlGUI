"""Headless tests for timed input replay + the input-sequence DSL. The sink
and sleep are injected, so nothing real is typed/clicked and timing is
deterministic. Pure stdlib; no Qt imports."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.input_macro import replay_timeline, run_sequence


def test_replay_timeline_honors_gaps_and_speed():
    events = [{"op": "key", "key": "a", "delta_ms": 0},
              {"op": "key", "key": "b", "delta_ms": 200}]
    gaps, sunk = [], []
    played = replay_timeline(
        events, speed=2.0, sink=lambda e: sunk.append(e["key"]),
        sleep=gaps.append)
    assert played == 2 and sunk == ["a", "b"]
    assert gaps == [pytest.approx(0.1)]      # 200ms / speed 2 = 0.1s; first=0


def test_replay_timeline_clamps_gap():
    events = [{"op": "click", "x": 1, "y": 2, "delta_ms": 5000}]
    gaps = []
    replay_timeline(events, sink=lambda e: None, sleep=gaps.append,
                    max_gap=0.5)
    assert gaps == [0.5]


def test_run_sequence_repeat_wait_and_chord():
    sunk, slept = [], []
    steps = [
        {"op": "press", "key": "ctrl"},
        {"op": "repeat", "times": 2, "steps": [{"op": "key", "key": "a"}]},
        {"op": "wait", "ms": 50},
        {"op": "release", "key": "ctrl"},
    ]
    log = run_sequence(
        steps, sink=lambda e: sunk.append(e.get("key") or e.get("op")),
        sleep=slept.append)
    assert sunk == ["ctrl", "a", "a", "ctrl"]   # wait/repeat not dispatched
    assert slept == [pytest.approx(0.05)]
    assert [s["op"] for s in log] == ["press", "key", "key", "wait", "release"]


# --- wiring (registration only — executing would do real input) ----------

def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_replay_timeline", "AC_input_sequence"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_replay_timeline", "ac_input_sequence"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_replay_timeline", "AC_input_sequence"} <= cmds


def test_facade_exports():
    for attr in ("replay_timeline", "run_sequence"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
