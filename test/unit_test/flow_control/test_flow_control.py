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
    ex, state = executor_with_hooks
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
