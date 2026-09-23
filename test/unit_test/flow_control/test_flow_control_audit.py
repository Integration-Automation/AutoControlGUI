"""Regression tests for the flow-control defects found in the 2026-09-23 audit.

Each one was reproduced against the previous code before it was fixed:
assertions neutralised by ``AC_parallel`` and an exhausted ``AC_retry``, loop
signals escaping the top level, unbounded macro recursion, empty bodies that
failed instead of doing nothing, and waits that never looked when the timeout
was zero.
"""
import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlAssertionException,
)
from je_auto_control.utils.executor import flow_control
from je_auto_control.utils.executor.action_executor import Executor

_SET_X = ["AC_set_var", {"name": "x", "value": 1}]
_ASSERT_X_IS_2 = ["AC_assert_var", {"name": "x", "value": 2}]


@pytest.fixture()
def ex():
    executor = Executor()
    executor.event_dict["AC_noop"] = lambda: "ran"
    return executor


def test_a_failed_assertion_in_a_parallel_branch_propagates(ex):
    with pytest.raises(AutoControlAssertionException):
        ex.execute_action([["AC_parallel", {"branches": [[_SET_X, _ASSERT_X_IS_2]]}]])


def test_a_parallel_branch_that_errors_is_still_recorded_not_raised(ex):
    # JSON-string branches are validated before any branch runs; the failure
    # is still recorded, not raised, under raise_on_error=False.
    record = ex.execute_action([["AC_parallel", {"branches": '[{"not": "a list"}]'}]])
    assert any("must be a list" in str(value) for value in record.values())


def test_an_empty_parallel_branch_is_a_no_op(ex):
    record = ex.execute_action([["AC_parallel", {"branches": [[], [["AC_noop"]]]}]])
    result = next(iter(record.values()))
    assert result["branches"] == 2 and result["results"][0] is None


def test_an_exhausted_retry_re_raises_the_assertion(ex):
    with pytest.raises(AutoControlAssertionException):
        ex.execute_action([_SET_X, ["AC_retry", {"max_attempts": 1, "backoff": 0,
                                                  "body": [_ASSERT_X_IS_2]}]])


def test_an_exhausted_retry_still_wraps_ordinary_errors(ex):
    record = ex.execute_action([["AC_retry", {"max_attempts": 1, "backoff": 0,
                                              "body": [["AC_call_macro", {"name": "missing"}]]}]])
    assert any("exhausted" in str(value) for value in record.values())


@pytest.mark.parametrize("signal", ["AC_break", "AC_continue"])
def test_a_loop_signal_outside_a_loop_is_a_recorded_failure(ex, signal):
    record = ex.execute_action([[signal], ["AC_noop"]])
    values = list(record.values())
    assert "outside a loop" in values[0]
    assert values[1] == "ran", "the rest of the script must still run"


def test_a_loop_signal_outside_a_loop_raises_when_asked(ex):
    with pytest.raises(AutoControlActionException, match="outside a loop"):
        ex.execute_action([["AC_break"]], raise_on_error=True)


def test_break_inside_a_macro_still_ends_the_enclosing_loop(ex):
    calls = []
    ex.event_dict["AC_count"] = lambda: calls.append(1)
    ex.execute_action([
        ["AC_define_macro", {"name": "stop", "body": [["AC_break"]]}],
        ["AC_loop", {"times": 5, "body": [["AC_count"], ["AC_call_macro", {"name": "stop"}]]}],
    ])
    assert calls == [1]


def test_a_self_calling_macro_stops_at_the_depth_limit(ex, monkeypatch):
    monkeypatch.setattr(flow_control, "MAX_MACRO_DEPTH", 5)
    script = [
        ["AC_define_macro", {"name": "m", "body": [["AC_call_macro", {"name": "m"}]]}],
        ["AC_call_macro", {"name": "m"}],
        ["AC_noop"],
    ]
    with pytest.raises(AutoControlActionException, match="nested deeper"):
        ex.execute_action(script, raise_on_error=True)
    assert getattr(flow_control._MACRO_DEPTH, "value", 0) == 0, "depth must unwind"
    # Without raise_on_error it is recorded at the top level, not buried
    # in the deepest body, and the rest of the script still runs.
    values = list(ex.execute_action(script).values())
    assert "nested deeper" in values[1] and values[2] == "ran"


def test_a_macro_without_a_body_is_a_no_op(ex):
    record = ex.execute_action([["AC_define_macro", {"name": "m"}],
                                ["AC_call_macro", {"name": "m"}]])
    assert list(record.values())[1] is None


def test_assert_duration_with_an_empty_body_is_a_no_op(ex):
    record = ex.execute_action([["AC_assert_duration", {"max_ms": 1000, "body": []}]])
    assert "Exception" not in str(next(iter(record.values())))


@pytest.mark.parametrize("command, probe, args", [
    ("AC_wait_image", "_image_present", {"image": "a.png", "timeout": 0}),
    ("AC_wait_pixel", "_pixel_matches", {"x": 1, "y": 1, "rgb": [0, 0, 0], "timeout": 0}),
])
def test_a_zero_timeout_wait_still_looks_once(ex, monkeypatch, command, probe, args):
    calls = []
    monkeypatch.setattr(flow_control, probe, lambda *a, **k: calls.append(1) or True)
    record = ex.execute_action([[command, args]])
    assert calls == [1]
    assert next(iter(record.values())) is True
