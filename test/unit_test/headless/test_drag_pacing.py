"""Drag pacing (``step_delay_s`` / ``settle_s``) and the release on failure.

``tween_drag`` and ``drag_path`` share one press / move / release sequence.
Every event goes to a recording sink and every pause to a recording clock, so
no real input is sent and nothing sleeps. No Qt imports.
"""
import importlib
import math
import types

import pytest

from je_auto_control.utils.mouse_path import drag_path
from je_auto_control.utils.tween_drag import tween_drag

tween_module = importlib.import_module("je_auto_control.utils.tween_drag.tween_drag")
path_module = importlib.import_module("je_auto_control.utils.mouse_path.mouse_path")


class _Timeline:
    """One ordered record of dispatched events and pauses."""

    def __init__(self, fail_on=None, error=RuntimeError):
        self.entries = []
        self.fail_on = fail_on or (lambda event, index: False)
        self.error = error

    def sink(self, event):
        index = sum(1 for kind, *_ in self.entries if kind == event["op"])
        self.entries.append((event["op"], event.get("x"), event.get("y")))
        if self.fail_on(event, index):
            raise self.error(f"{event['op']} #{index} failed")

    def sleep(self, seconds):
        self.entries.append(("sleep", seconds, None))

    def ops(self):
        return [kind for kind, *_ in self.entries]


@pytest.fixture()
def timeline(monkeypatch):
    line = _Timeline()
    monkeypatch.setattr(tween_module, "time", types.SimpleNamespace(sleep=line.sleep))
    return line


def _linear(start, end, **kwargs):
    return tween_drag(start, end, steps=2, easing="linear", **kwargs)


# --- defaults: the old event sequence, no pauses -------------------------------

def test_defaults_dispatch_press_moves_release_and_never_sleep(timeline):
    out = _linear((0, 0), (10, 0), sink=timeline.sink)
    assert timeline.entries == [("press", 0, 0), ("move", 0, 0), ("move", 5, 0),
                                ("move", 10, 0), ("release", 10, 0)]
    assert out["points"] == 3


def test_drag_path_defaults_are_unchanged_too(timeline):
    drag_path([(0, 0), (4, 0)], per_segment_steps=2, sink=timeline.sink)
    assert timeline.ops() == ["press", "move", "move", "move", "release"]


# --- pacing ----------------------------------------------------------------------

def test_step_delay_pauses_after_every_move(timeline):
    _linear((0, 0), (10, 0), sink=timeline.sink, step_delay_s=0.012)
    assert timeline.ops() == ["press", "move", "sleep", "move", "sleep",
                              "move", "sleep", "release"]
    assert {seconds for kind, seconds, _ in timeline.entries if kind == "sleep"} == {0.012}


def test_settle_rests_on_the_start_and_around_the_press_and_release(timeline):
    _linear((0, 0), (10, 0), sink=timeline.sink, settle_s=0.08)
    assert timeline.entries == [
        ("move", 0, 0), ("sleep", 0.08, None),        # hover on the start
        ("press", 0, 0), ("sleep", 0.08, None),       # after the press
        ("move", 0, 0), ("move", 5, 0), ("move", 10, 0),
        ("sleep", 0.08, None),                         # before the release
        ("release", 10, 0)]


def test_drag_path_takes_the_same_pacing(timeline):
    drag_path([(0, 0), (2, 0), (2, 2)], per_segment_steps=1, sink=timeline.sink,
              step_delay_s=0.01, settle_s=0.05)
    assert timeline.ops() == ["move", "sleep", "press", "sleep",
                              "move", "sleep", "move", "sleep", "move", "sleep",
                              "sleep", "release"]


@pytest.mark.parametrize("name", ["step_delay_s", "settle_s"])
@pytest.mark.parametrize("value", [-0.01, math.nan, math.inf, "soon", None])
def test_an_invalid_pause_is_refused_before_anything_is_sent(timeline, name, value):
    with pytest.raises(ValueError):
        _linear((0, 0), (10, 0), sink=timeline.sink, **{name: value})
    with pytest.raises(ValueError):
        drag_path([(0, 0), (4, 0)], sink=timeline.sink, **{name: value})
    assert timeline.entries == []


def test_an_empty_path_sends_nothing_even_with_pacing(timeline):
    assert drag_path([], sink=timeline.sink, settle_s=1.0)["points"] == 0
    assert timeline.entries == []


# --- the release when a step raises ----------------------------------------------

def test_a_failed_move_releases_at_the_last_point_reached(timeline):
    timeline.fail_on = lambda event, index: event["op"] == "move" and index == 2
    with pytest.raises(RuntimeError, match="move #2"):
        _linear((0, 0), (10, 0), sink=timeline.sink)
    # The move to (10, 0) failed: let go at (5, 0), not at the drop target.
    assert timeline.entries[-1] == ("release", 5, 0)
    assert timeline.ops().count("release") == 1


def test_a_failure_on_the_first_move_releases_where_it_was_pressed(timeline):
    timeline.fail_on = lambda event, index: event["op"] == "move" and index == 0
    with pytest.raises(RuntimeError):
        drag_path([(3, 4), (9, 9)], per_segment_steps=2, sink=timeline.sink)
    assert timeline.entries[-1] == ("release", 3, 4)


def test_a_failed_press_releases_nothing(timeline):
    timeline.fail_on = lambda event, index: event["op"] == "press"
    with pytest.raises(RuntimeError):
        _linear((0, 0), (10, 0), sink=timeline.sink)
    assert "release" not in timeline.ops()


def test_an_interrupted_pause_still_releases(timeline, monkeypatch):
    def interrupt(seconds):
        timeline.entries.append(("sleep", seconds, None))
        if timeline.ops().count("move") == 2:
            raise KeyboardInterrupt
    monkeypatch.setattr(tween_module, "time", types.SimpleNamespace(sleep=interrupt))
    with pytest.raises(KeyboardInterrupt):
        _linear((0, 0), (10, 0), sink=timeline.sink, step_delay_s=0.01)
    assert timeline.entries[-1] == ("release", 5, 0)


def test_a_failing_cleanup_release_does_not_hide_the_original_error(timeline):
    def fail(event, index):
        return (event["op"] == "move" and index == 1) or event["op"] == "release"
    timeline.fail_on = fail
    with pytest.raises(RuntimeError, match="move #1"):
        _linear((0, 0), (10, 0), sink=timeline.sink)
    assert timeline.entries[-1] == ("release", 0, 0)


def test_a_failing_final_release_is_raised_and_retried_once(timeline):
    timeline.fail_on = lambda event, index: event["op"] == "release" and index == 0
    with pytest.raises(RuntimeError, match="release #0"):
        _linear((0, 0), (10, 0), sink=timeline.sink)
    assert timeline.entries[-2:] == [("release", 10, 0), ("release", 10, 0)]


# --- wiring ----------------------------------------------------------------------

def test_the_executor_adapters_forward_the_pacing(timeline, monkeypatch):
    from je_auto_control.utils.executor import action_executor
    monkeypatch.setattr(tween_module, "_default_sink", timeline.sink)
    monkeypatch.setattr(path_module, "_default_sink", timeline.sink)
    action_executor._tween_drag([0, 0], [10, 0], steps=1, easing="linear",
                                step_delay_s=0.02, settle_s="0.03")
    assert ("sleep", 0.02, None) in timeline.entries and ("sleep", 0.03, None) in timeline.entries
    timeline.entries.clear()
    action_executor._drag_path([[0, 0], [5, 5]], per_segment_steps=1, step_delay_s=0.04)
    assert ("sleep", 0.04, None) in timeline.entries


def test_the_mcp_handlers_forward_the_pacing(timeline, monkeypatch):
    from je_auto_control.utils.mcp_server.tools import _handlers, _handlers_executor_bridge
    monkeypatch.setattr(tween_module, "_default_sink", timeline.sink)
    monkeypatch.setattr(path_module, "_default_sink", timeline.sink)
    assert _handlers.tween_drag([0, 0], [10, 0], steps=1, settle_s=0.05) == {"points": 2}
    assert ("sleep", 0.05, None) in timeline.entries
    timeline.entries.clear()
    _handlers_executor_bridge.drag_path([[0, 0], [5, 5]], per_segment_steps=1, step_delay_s=0.06)
    assert ("sleep", 0.06, None) in timeline.entries


def test_the_mcp_tools_and_script_builder_declare_the_pacing():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    specs = {spec.command: spec for spec in _build_specs()}
    for tool, command in (("ac_tween_drag", "AC_tween_drag"), ("ac_drag_path", "AC_drag_path")):
        assert {"step_delay_s", "settle_s"} <= set(tools[tool].input_schema["properties"])
        assert {"step_delay_s", "settle_s"} <= {field.name for field in specs[command].fields}
