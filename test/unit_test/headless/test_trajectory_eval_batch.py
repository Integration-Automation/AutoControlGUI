"""Headless tests for agent trajectory evaluation. Pure stdlib, no Qt imports."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.trajectory_eval import evaluate_trajectory

TRAJ = [
    {"action": "AC_focus_window", "observation": "focused"},
    {"action": "AC_type_text", "args": {"text": "hi"}, "observation": "typed"},
    {"action": "AC_click_mouse", "observation": "Saved successfully"},
]


def test_empty_rubric_passes():
    result = evaluate_trajectory(TRAJ, {})
    assert result["passed"] is True
    assert result["score"] == pytest.approx(1.0)
    assert result["steps"] == 3


def test_required_actions_present():
    result = evaluate_trajectory(TRAJ, {"required_actions": ["AC_type_text",
                                                             "AC_click_mouse"]})
    assert result["passed"] is True


def test_required_actions_missing_fails():
    result = evaluate_trajectory(TRAJ, {"required_actions": ["AC_hotkey"]})
    assert result["passed"] is False
    assert result["score"] == pytest.approx(0.0)


def test_ordered_requirement():
    ordered_ok = {"required_actions": ["AC_focus_window", "AC_click_mouse"],
                  "ordered": True}
    assert evaluate_trajectory(TRAJ, ordered_ok)["passed"] is True
    ordered_bad = {"required_actions": ["AC_click_mouse", "AC_focus_window"],
                   "ordered": True}
    assert evaluate_trajectory(TRAJ, ordered_bad)["passed"] is False


def test_forbidden_actions():
    assert evaluate_trajectory(
        TRAJ, {"forbidden_actions": ["AC_kill_process"]})["passed"] is True
    assert evaluate_trajectory(
        TRAJ, {"forbidden_actions": ["AC_click_mouse"]})["passed"] is False


def test_max_steps():
    assert evaluate_trajectory(TRAJ, {"max_steps": 3})["passed"] is True
    assert evaluate_trajectory(TRAJ, {"max_steps": 2})["passed"] is False


def test_success_contains():
    assert evaluate_trajectory(
        TRAJ, {"success_contains": "Saved"})["passed"] is True
    assert evaluate_trajectory(
        TRAJ, {"success_contains": "Error"})["passed"] is False


def test_partial_score():
    rubric = {"required_actions": ["AC_type_text"],   # pass
              "forbidden_actions": ["AC_type_text"]}   # fail
    result = evaluate_trajectory(TRAJ, rubric)
    assert result["passed"] is False
    assert result["score"] == pytest.approx(0.5)


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip_with_json_strings():
    rec = ac.execute_action([[
        "AC_evaluate_trajectory",
        {"trajectory": json.dumps(TRAJ),
         "rubric": json.dumps({"required_actions": ["AC_type_text"]})},
    ]])
    assert any(v.get("passed") is True for v in rec.values()
               if isinstance(v, dict))


def test_wiring():
    assert "AC_evaluate_trajectory" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_evaluate_trajectory" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert "AC_evaluate_trajectory" in cmds


def test_facade_export():
    assert hasattr(ac, "evaluate_trajectory")
    assert "evaluate_trajectory" in ac.__all__
