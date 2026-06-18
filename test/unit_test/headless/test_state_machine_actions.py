"""Headless tests for the state-machine action wiring (AC_run_state_machine)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.state_machine import StateMachineError, run_state_machine


def _spec(extra=None):
    spec = {
        "initial": "start",
        "states": {
            "start": {"transitions": [{"go_to": "done"}]},
            "done": {"final": True},
        },
    }
    if extra:
        spec.update(extra)
    return spec


def test_run_reaches_final_state():
    result = run_state_machine(_spec())
    assert result["final_state"] == "done"
    assert result["steps"] == 1


def test_invalid_spec_raises():
    with pytest.raises(StateMachineError):
        run_state_machine({"states": {}})  # missing 'initial'


def test_no_fireable_transition_raises():
    spec = {"initial": "a",
            "states": {"a": {"transitions": [{"go_to": "a",
                                              "after": 999}]}}}
    with pytest.raises(StateMachineError):
        run_state_machine({**spec, "max_steps": 1})


def test_facade_and_executor_wiring():
    assert ac.run_state_machine is run_state_machine
    assert "AC_run_state_machine" in ac.executor.known_commands()
    record = ac.execute_action(
        [["AC_run_state_machine", {"spec": _spec()}]])
    assert any("done" in str(v) for v in record.values())


def test_mcp_tool_registered():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_run_state_machine" in names
