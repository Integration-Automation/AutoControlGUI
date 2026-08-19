"""Tests for flow extensions: assert_duration, AC_parallel, macros."""
import time

import pytest

from je_auto_control.utils.assertion.assertions import assert_duration
from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException,
)
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.flow_control import (
    exec_call_macro, exec_parallel,
)
from je_auto_control.utils.executor.flow_data_commands import (
    exec_assert_duration,
)


# --- assert_duration --------------------------------------------------------

def test_assert_duration_passes_under_budget():
    result = assert_duration(lambda: None, max_ms=1000, raise_on_fail=False)
    assert result.passed is True
    assert result.kind == "duration"


def test_assert_duration_fails_over_budget():
    result = assert_duration(
        lambda: time.sleep(0.03), max_ms=1, raise_on_fail=False,
    )
    assert result.passed is False
    assert result.actual["elapsed_ms"] >= 1.0


def test_ac_assert_duration_times_the_body():
    result = exec_assert_duration(Executor(), {
        "max_ms": 5000,
        "body": [["AC_set_var", {"name": "x", "value": 1}]],
    })
    assert result["passed"] is True
    assert result["kind"] == "duration"


# --- AC_parallel ------------------------------------------------------------

def test_parallel_runs_every_branch():
    result = exec_parallel(Executor(), {"branches": [
        [["AC_set_var", {"name": "a", "value": 1}]],
        [["AC_set_var", {"name": "b", "value": 2}]],
        [["AC_set_var", {"name": "c", "value": 3}]],
    ]})
    assert result["branches"] == 3
    assert len(result["results"]) == 3
    assert all(branch is not None for branch in result["results"])


def test_parallel_accepts_json_string_branches():
    result = exec_parallel(Executor(), {
        "branches": '[[["AC_set_var", {"name": "x", "value": 1}]]]',
    })
    assert result["branches"] == 1


# --- macros -----------------------------------------------------------------

def test_macro_define_then_call_binds_params():
    executor = Executor()
    executor.execute_action([["AC_define_macro", {
        "name": "greet", "params": ["who"],
        "body": [["AC_set_var", {"name": "out", "value": "hi ${who}"}]],
    }]])
    assert "greet" in executor.macros
    executor.execute_action(
        [["AC_call_macro", {"name": "greet", "args": {"who": "Sam"}}]],
    )
    assert executor.variables.get_value("out") == "hi Sam"


def test_define_macro_accepts_comma_separated_params():
    executor = Executor()
    executor.execute_action([["AC_define_macro", {
        "name": "m", "params": "x, y", "body": [],
    }]])
    assert executor.macros["m"]["params"] == ["x", "y"]


def test_call_unknown_macro_raises():
    with pytest.raises(AutoControlActionException):
        exec_call_macro(Executor(), {"name": "does-not-exist"})
