"""Phase 7.2: declarative FSM engine tests."""
import time

import pytest

from je_auto_control.utils.state_machine import (
    StateMachine, StateMachineError, run_state_machine,
)


def _capture_executor():
    """Returns (execute_action_fn, captured_list)."""
    captured = []
    return (lambda action: captured.append(action)), captured


# --- happy path -------------------------------------------------------

def test_runs_simple_two_state_flow():
    execute, captured = _capture_executor()
    spec = {
        "initial": "start",
        "states": {
            "start": {
                "on_enter": [["AC_screenshot", {"file_path": "boot.png"}]],
                "transitions": [{"go_to": "done"}],
            },
            "done": {"final": True},
        },
    }
    result = StateMachine(spec, execute_action=execute).run()
    assert result["final_state"] == "done"
    assert result["steps"] == 1
    assert captured == [["AC_screenshot", {"file_path": "boot.png"}]]


def test_run_state_machine_convenience_wrapper():
    execute, _ = _capture_executor()
    spec = {
        "initial": "done",
        "states": {"done": {"final": True}},
    }
    result = run_state_machine(spec, execute_action=execute)
    assert result["final_state"] == "done"


# --- guards ----------------------------------------------------------

def test_if_var_eq_guard_routes_to_matching_branch():
    execute, _ = _capture_executor()
    spec = {
        "initial": "check",
        "states": {
            "check": {
                "transitions": [
                    {"if_var_eq": {"name": "color", "value": "red"},
                     "go_to": "red_branch"},
                    {"go_to": "default"},
                ],
            },
            "red_branch": {"final": True},
            "default": {"final": True},
        },
    }
    fsm = StateMachine(spec, execute_action=execute)
    fsm.context["color"] = "red"
    assert fsm.run()["final_state"] == "red_branch"


def test_if_var_eq_falls_through_to_default_when_no_match():
    execute, _ = _capture_executor()
    spec = {
        "initial": "check",
        "states": {
            "check": {
                "transitions": [
                    {"if_var_eq": {"name": "color", "value": "red"},
                     "go_to": "red"},
                    {"go_to": "default"},
                ],
            },
            "red": {"final": True},
            "default": {"final": True},
        },
    }
    fsm = StateMachine(spec, execute_action=execute)
    fsm.context["color"] = "blue"
    assert fsm.run()["final_state"] == "default"


def test_predicate_guard_called_with_context():
    execute, _ = _capture_executor()
    seen_contexts = []

    def predicate(ctx):
        seen_contexts.append(dict(ctx))
        return ctx.get("ready") is True

    spec = {
        "initial": "wait",
        "states": {
            "wait": {
                "transitions": [
                    {"predicate": predicate, "go_to": "done"},
                    {"go_to": "wait"},  # would loop forever w/o max_steps
                ],
            },
            "done": {"final": True},
        },
        "max_steps": 5,
    }
    fsm = StateMachine(spec, execute_action=execute)
    fsm.context["ready"] = True
    fsm.run()
    assert len(seen_contexts) == 1


def test_custom_guard_eval_overrides_default():
    execute, _ = _capture_executor()

    def always_first(_trans, _ctx, _started):
        return True

    spec = {
        "initial": "fork",
        "states": {
            "fork": {
                "transitions": [
                    {"if_var_eq": {"name": "missing", "value": "x"},
                     "go_to": "left"},
                    {"go_to": "right"},
                ],
            },
            "left": {"final": True},
            "right": {"final": True},
        },
    }
    fsm = StateMachine(spec, execute_action=execute,
                       guard_eval=always_first)
    assert fsm.run()["final_state"] == "left"


# --- budgets ---------------------------------------------------------

def test_max_steps_exhausts_raises():
    execute, _ = _capture_executor()
    spec = {
        "initial": "loop",
        "states": {
            "loop": {
                "transitions": [{"go_to": "loop"}],
            },
        },
        "max_steps": 3,
    }
    with pytest.raises(StateMachineError, match="max_steps"):
        StateMachine(spec, execute_action=execute).run()


def test_global_timeout_exhausts_raises():
    """Force a long-running state by sleeping inside the guard."""
    execute, _ = _capture_executor()

    def slow_guard(_trans, _ctx, _started):
        time.sleep(0.02)
        return False

    spec = {
        "initial": "loop",
        "states": {
            "loop": {"transitions": [{"go_to": "loop"}]},
        },
        "max_steps": 10_000,
        "global_timeout_s": 0.05,
    }
    with pytest.raises(StateMachineError):
        StateMachine(
            spec, execute_action=execute, guard_eval=slow_guard,
        ).run()


def test_no_fireable_transition_raises():
    execute, _ = _capture_executor()
    spec = {
        "initial": "stuck",
        "states": {
            "stuck": {
                "transitions": [
                    {"if_var_eq": {"name": "x", "value": 1}, "go_to": "x"},
                ],
            },
            "x": {"final": True},
        },
    }
    with pytest.raises(StateMachineError, match="no transition fired"):
        StateMachine(spec, execute_action=execute).run()


# --- validation ------------------------------------------------------

def test_missing_initial_raises():
    with pytest.raises(StateMachineError, match="'initial'"):
        StateMachine({"states": {}})


def test_unknown_initial_state_raises():
    spec = {"initial": "nowhere", "states": {"done": {"final": True}}}
    with pytest.raises(StateMachineError, match="initial state"):
        StateMachine(spec).run()


def test_transition_to_undefined_state_raises():
    spec = {
        "initial": "a",
        "states": {
            "a": {"transitions": [{"go_to": "z"}]},
        },
    }
    with pytest.raises(StateMachineError, match="undefined state"):
        StateMachine(spec).run()


def test_non_mapping_spec_raises():
    with pytest.raises(StateMachineError):
        StateMachine([])  # type: ignore[arg-type]  # NOSONAR python:S5655  # reason: intentional bad-type negative test
