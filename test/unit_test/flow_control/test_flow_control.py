"""Unit tests for flow-control executor commands and schema validation."""
import time

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException,
)
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.action_schema import validate_actions


@pytest.fixture()
def executor_with_hooks():
    """Return a fresh Executor plus a mutable counter for assertions."""
    executor = Executor()
    state = {"count": 0, "last_error": None}

    def noop():
        state["count"] += 1
        return state["count"]

    executor.event_dict["AC_noop"] = noop
    return executor, state


def test_ac_loop_runs_body_exact_times(executor_with_hooks):
    ex, state = executor_with_hooks
    ex.execute_action([["AC_loop", {"times": 4, "body": [["AC_noop"]]}]])
    assert state["count"] == 4


def test_ac_break_exits_loop_early(executor_with_hooks):
    ex, state = executor_with_hooks
    ex.execute_action([["AC_loop", {"times": 10,
                                    "body": [["AC_noop"], ["AC_break"]]}]])
    assert state["count"] == 1


def test_ac_continue_does_not_stop_loop(executor_with_hooks):
    ex, state = executor_with_hooks
    ex.execute_action([["AC_loop", {"times": 3,
                                    "body": [["AC_continue"], ["AC_noop"]]}]])
    assert state["count"] == 0


def test_ac_sleep_delays(executor_with_hooks):
    ex, _ = executor_with_hooks
    start = time.monotonic()
    ex.execute_action([["AC_sleep", {"seconds": 0.05}]])
    assert time.monotonic() - start >= 0.04


def test_ac_wait_image_times_out(monkeypatch, executor_with_hooks):
    ex, _ = executor_with_hooks
    from je_auto_control.utils.executor import flow_control

    monkeypatch.setattr(flow_control, "_image_present", lambda *a, **k: False)
    result = ex.execute_action([
        ["AC_wait_image", {"image": "x.png", "timeout": 0.1, "poll": 0.01}],
    ])
    # error is captured in the record dict, not raised
    assert any("timeout" in repr(v).lower() for v in result.values())


def test_ac_retry_succeeds_after_failures(executor_with_hooks):
    ex, _ = executor_with_hooks
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("not yet")
        return "ok"

    ex.event_dict["AC_flaky"] = flaky
    ex.execute_action([["AC_retry", {
        "max_attempts": 5, "backoff": 0.001, "body": [["AC_flaky"]]
    }]])
    assert attempts["n"] == 3


def test_ac_retry_exhausts_and_records_error(executor_with_hooks):
    ex, _ = executor_with_hooks

    def always_fail():
        raise RuntimeError("boom")

    ex.event_dict["AC_failer"] = always_fail
    result = ex.execute_action([["AC_retry", {
        "max_attempts": 2, "backoff": 0.001, "body": [["AC_failer"]]
    }]])
    assert any("exhausted" in repr(v) for v in result.values())


def test_schema_rejects_unknown_command(executor_with_hooks):
    ex, _ = executor_with_hooks
    with pytest.raises(AutoControlActionException):
        ex.execute_action([["AC_does_not_exist", {}]])


def test_schema_validates_nested_body(executor_with_hooks):
    ex, _ = executor_with_hooks
    with pytest.raises(AutoControlActionException):
        ex.execute_action([["AC_loop", {
            "times": 1, "body": [["AC_nonexistent"]]
        }]])


def test_validate_actions_accepts_valid_payload():
    validate_actions(
        [["AC_loop", {"times": 1, "body": []}]],
        {"AC_loop"},
    )


def test_validate_actions_rejects_non_list():
    with pytest.raises(AutoControlActionException):
        validate_actions("not a list", {"AC_loop"})


def test_validate_actions_rejects_wrong_body_type():
    with pytest.raises(AutoControlActionException):
        validate_actions(
            [["AC_loop", {"times": 1, "body": "not a list"}]],
            {"AC_loop"},
        )


def test_if_image_found_selects_then_branch(monkeypatch, executor_with_hooks):
    ex, state = executor_with_hooks
    from je_auto_control.utils.executor import flow_control

    monkeypatch.setattr(flow_control, "_image_present", lambda *a, **k: True)
    ex.execute_action([["AC_if_image_found", {
        "image": "x.png", "then": [["AC_noop"]], "else": []
    }]])
    assert state["count"] == 1


def test_if_image_found_selects_else_branch(monkeypatch, executor_with_hooks):
    ex, state = executor_with_hooks
    from je_auto_control.utils.executor import flow_control

    monkeypatch.setattr(flow_control, "_image_present", lambda *a, **k: False)
    ex.execute_action([["AC_if_image_found", {
        "image": "x.png", "then": [], "else": [["AC_noop"]]
    }]])
    assert state["count"] == 1


def test_ac_set_var_stores_value(executor_with_hooks):
    ex, _ = executor_with_hooks
    ex.execute_action([["AC_set_var", {"name": "greeting", "value": "hi"}]])
    assert ex.variables.get_value("greeting") == "hi"


def test_ac_inc_var_increments_default_zero(executor_with_hooks):
    ex, _ = executor_with_hooks
    ex.execute_action([
        ["AC_inc_var", {"name": "counter"}],
        ["AC_inc_var", {"name": "counter", "by": 4}],
    ])
    assert ex.variables.get_value("counter") == 5


def test_runtime_interpolation_uses_current_scope(executor_with_hooks):
    ex, _ = executor_with_hooks
    seen = []
    ex.event_dict["AC_capture"] = lambda payload: seen.append(payload)
    ex.execute_action([
        ["AC_set_var", {"name": "msg", "value": "hello"}],
        ["AC_capture", {"payload": "${msg}"}],
    ])
    assert seen == ["hello"]


def test_runtime_interpolation_preserves_value_type(executor_with_hooks):
    ex, _ = executor_with_hooks
    seen = []
    ex.event_dict["AC_capture"] = lambda payload: seen.append(payload)
    ex.execute_action([
        ["AC_set_var", {"name": "n", "value": 42}],
        ["AC_capture", {"payload": "${n}"}],
    ])
    assert len(seen) == 1
    assert seen[0] == 42
    assert isinstance(seen[0], int)


def test_ac_if_var_eq_runs_then(executor_with_hooks):
    ex, state = executor_with_hooks
    ex.execute_action([
        ["AC_set_var", {"name": "x", "value": 5}],
        ["AC_if_var", {
            "name": "x", "op": "eq", "value": 5,
            "then": [["AC_noop"]], "else": [],
        }],
    ])
    assert state["count"] == 1


def test_ac_if_var_lt_picks_else_when_false(executor_with_hooks):
    ex, state = executor_with_hooks
    ex.execute_action([
        ["AC_set_var", {"name": "x", "value": 9}],
        ["AC_if_var", {
            "name": "x", "op": "lt", "value": 5,
            "then": [["AC_noop"]], "else": [["AC_noop"], ["AC_noop"]],
        }],
    ])
    assert state["count"] == 2


def test_ac_if_var_unknown_op_raises(executor_with_hooks):
    ex, _ = executor_with_hooks
    with pytest.raises(AutoControlActionException):
        ex.execute_action([
            ["AC_if_var", {
                "name": "x", "op": "wat", "value": 1,
                "then": [], "else": [],
            }],
        ], raise_on_error=True)


def test_ac_for_each_iterates_items(executor_with_hooks):
    ex, _ = executor_with_hooks
    seen = []
    ex.event_dict["AC_capture"] = lambda payload: seen.append(payload)
    ex.execute_action([
        ["AC_for_each", {
            "items": ["a", "b", "c"], "as": "letter",
            "body": [["AC_capture", {"payload": "${letter}"}]],
        }],
    ])
    assert seen == ["a", "b", "c"]


def test_ac_for_each_break_stops_iteration(executor_with_hooks):
    ex, state = executor_with_hooks
    ex.execute_action([
        ["AC_for_each", {
            "items": [1, 2, 3, 4], "as": "n",
            "body": [
                ["AC_if_var", {
                    "name": "n", "op": "ge", "value": 3,
                    "then": [["AC_break"]], "else": [["AC_noop"]],
                }],
            ],
        }],
    ])
    assert state["count"] == 2


def test_deferred_args_keep_placeholders_for_each_iteration(executor_with_hooks):
    """Body must re-resolve ${var} per iteration, not freeze first value."""
    ex, _ = executor_with_hooks
    seen = []
    ex.event_dict["AC_capture"] = lambda payload: seen.append(payload)
    ex.execute_action([
        ["AC_for_each", {
            "items": [10, 20, 30], "as": "v",
            "body": [["AC_capture", {"payload": "${v}"}]],
        }],
    ])
    assert seen == [10, 20, 30]
