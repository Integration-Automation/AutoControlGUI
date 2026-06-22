"""Headless tests for multi-waypoint mouse gestures. No Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.mouse_path import (
    drag_path, move_along_path, path_easings, plan_path,
)


def test_plan_path_through_waypoints_dedups_junctions():
    points = plan_path([(0, 0), (10, 0), (10, 10)], per_segment_steps=5)
    assert points[0] == [0, 0] and points[-1] == [10, 10]
    assert len(points) == 11                     # 5 + 5 + shared junction once
    assert points.count([10, 0]) == 1            # junction not duplicated


def test_plan_path_single_and_empty():
    assert plan_path([(3, 4)]) == [[3, 4]]
    assert plan_path([]) == []


def test_move_along_path_emits_only_moves():
    events = []
    result = move_along_path([(0, 0), (2, 2)], per_segment_steps=2,
                             sink=events.append)
    assert all(e["op"] == "move" for e in events)
    assert result["points"] == len(events) == 3


def test_drag_path_press_first_release_last():
    events = []
    drag_path([(0, 0), (5, 5), (5, 0)], per_segment_steps=2,
              sink=events.append)
    assert events[0]["op"] == "press" and (events[0]["x"], events[0]["y"]) == (0, 0)
    assert events[-1]["op"] == "release" and (events[-1]["x"], events[-1]["y"]) == (5, 0)
    assert [e["op"] for e in events[1:-1]] == ["move"] * (len(events) - 2)


def test_drag_path_empty_waypoints_noop():
    events = []
    result = drag_path([], sink=events.append)
    assert result["points"] == 0 and events == []


def test_easing_changes_intermediate_points():
    linear = plan_path([(0, 0), (100, 0)], easing="linear", per_segment_steps=10)
    eased = plan_path([(0, 0), (100, 0)], easing="ease_in_cubic",
                      per_segment_steps=10)
    assert linear[0] == eased[0] and linear[-1] == eased[-1]
    assert linear[5] != eased[5]                 # different curve mid-path
    assert "linear" in path_easings()


# --- wiring ---------------------------------------------------------------

def test_executor_waypoint_coercion():
    # the executor's backend dispatch is device-bound; exercise the adapter's
    # JSON-string -> list coercion (the part that runs before any real input).
    from je_auto_control.utils.executor.action_executor import _waypoints
    assert _waypoints(json.dumps([[0, 0], [4, 4]])) == [[0, 0], [4, 4]]
    assert _waypoints([[1, 2]]) == [[1, 2]]            # already a list


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_move_along_path", "AC_drag_path"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_move_along_path", "ac_drag_path"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_move_along_path", "AC_drag_path"} <= specs


def test_facade_exports():
    for attr in ("plan_path", "move_along_path", "drag_path", "path_easings"):
        assert hasattr(ac, attr) and attr in ac.__all__
