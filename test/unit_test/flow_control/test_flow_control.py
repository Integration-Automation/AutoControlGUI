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


# === AC_while_var ==========================================================

def test_ac_while_var_counts_up(executor_with_hooks):
    ex, state = executor_with_hooks
    ex.execute_action([
        ["AC_set_var", {"name": "i", "value": 0}],
        ["AC_while_var", {
            "name": "i", "op": "lt", "value": 3,
            "body": [["AC_noop"], ["AC_inc_var", {"name": "i"}]],
        }],
    ])
    assert state["count"] == 3
    assert ex.variables.get_value("i") == 3


def test_ac_while_var_false_initially_runs_zero_times(executor_with_hooks):
    ex, state = executor_with_hooks
    ex.execute_action([
        ["AC_set_var", {"name": "i", "value": 9}],
        ["AC_while_var", {
            "name": "i", "op": "lt", "value": 3,
            "body": [["AC_noop"]],
        }],
    ])
    assert state["count"] == 0


def test_ac_while_var_max_iter_caps_runaway(executor_with_hooks):
    ex, state = executor_with_hooks
    # condition never becomes false (i is never mutated) -> capped at max_iter
    ex.execute_action([
        ["AC_set_var", {"name": "i", "value": 0}],
        ["AC_while_var", {
            "name": "i", "op": "lt", "value": 3, "max_iter": 5,
            "body": [["AC_noop"]],
        }],
    ])
    assert state["count"] == 5


def test_ac_while_var_break_stops(executor_with_hooks):
    ex, state = executor_with_hooks
    ex.execute_action([
        ["AC_set_var", {"name": "i", "value": 0}],
        ["AC_while_var", {
            "name": "i", "op": "lt", "value": 100,
            "body": [["AC_noop"], ["AC_break"]],
        }],
    ])
    assert state["count"] == 1


def test_ac_while_var_unknown_op_raises(executor_with_hooks):
    ex, _ = executor_with_hooks
    with pytest.raises(AutoControlActionException):
        ex.execute_action([
            ["AC_while_var", {
                "name": "i", "op": "wat", "value": 1, "body": [],
            }],
        ], raise_on_error=True)


# === AC_try (try / catch / finally) ========================================

@pytest.fixture()
def executor_try():
    """Executor with a noop, a failer, and a capture hook for try tests."""
    executor = Executor()
    state = {"log": []}
    executor.event_dict["AC_ok"] = lambda: state["log"].append("ok")
    executor.event_dict["AC_recover"] = lambda: state["log"].append("recover")
    executor.event_dict["AC_cleanup"] = lambda: state["log"].append("cleanup")

    def boom():
        raise RuntimeError("boom")

    executor.event_dict["AC_boom"] = boom
    return executor, state


def test_ac_try_success_skips_catch_runs_finally(executor_try):
    ex, state = executor_try
    ex.execute_action([["AC_try", {
        "body": [["AC_ok"]],
        "catch": [["AC_recover"]],
        "finally": [["AC_cleanup"]],
    }]])
    assert state["log"] == ["ok", "cleanup"]


def test_ac_try_catch_runs_on_failure(executor_try):
    ex, state = executor_try
    ex.execute_action([["AC_try", {
        "body": [["AC_boom"]],
        "catch": [["AC_recover"]],
        "finally": [["AC_cleanup"]],
    }]])
    assert state["log"] == ["recover", "cleanup"]


def test_ac_try_exposes_error_to_var(executor_try):
    ex, _ = executor_try
    ex.execute_action([["AC_try", {
        "body": [["AC_boom"]],
        "error_var": "err",
        "catch": [],
    }]])
    assert "boom" in str(ex.variables.get_value("err"))


def test_ac_try_catch_resolves_error_var_with_a_populated_scope(executor_try):
    """``catch`` must interpolate ${err} lazily, after the body has failed.

    Regression: ``catch``/``finally`` were missing from the executor's
    deferred-arg keys, so they were interpolated eagerly at dispatch — before
    ``error_var`` was bound. That only showed up once the scope was non-empty,
    because an empty scope skipped interpolation entirely and masked it.
    """
    ex, _ = executor_try
    ex.execute_action([["AC_set_var", {"name": "unrelated", "value": 1}]])
    ex.execute_action([["AC_try", {
        "body": [["AC_boom"]],
        "error_var": "err",
        "catch": [["AC_set_var", {"name": "seen", "value": "${err}"}]],
    }]])
    assert "boom" in str(ex.variables.get_value("seen"))


def test_ac_try_finally_resolves_var_set_by_body(executor_try):
    """``finally`` must interpolate against state the body produced."""
    ex, _ = executor_try
    ex.execute_action([["AC_set_var", {"name": "unrelated", "value": 1}]])
    ex.execute_action([["AC_try", {
        "body": [["AC_set_var", {"name": "made_by_body", "value": "ok"}]],
        "finally": [["AC_set_var", {"name": "copied",
                                    "value": "${made_by_body}"}]],
    }]])
    assert ex.variables.get_value("copied") == "ok"


def test_unknown_var_raises_even_when_scope_is_empty():
    """An empty scope must not disable interpolation.

    Regression: ``_resolve_runtime_args`` short-circuited on a falsy (empty)
    scope, so placeholders reached the automation as literal text instead of
    raising — the opposite of the documented fail-fast contract.
    """
    ex = Executor()
    assert not ex.variables
    with pytest.raises(ValueError, match="Unknown variable"):
        ex.execute_action(
            [["AC_set_var", {"name": "x", "value": "${nope}"}]],
            raise_on_error=True,
        )


def test_secret_placeholder_is_never_passed_through_literally():
    """``${secrets.*}`` resolves via the vault and never needs the scope.

    With an empty scope this silently stored the literal ``${secrets.NAME}``,
    which would have been typed/sent verbatim in place of the secret.
    """
    ex = Executor()
    assert not ex.variables
    with pytest.raises(ValueError) as caught:
        ex.execute_action(
            [["AC_set_var", {"name": "grabbed", "value": "${secrets.NOPE}"}]],
            raise_on_error=True,
        )
    # Reaching the vault at all is the point: locked/unknown are both fine,
    # silently storing the placeholder is not.
    assert "secrets.NOPE" in str(caught.value)
    assert ex.variables.get_value("grabbed") != "${secrets.NOPE}"


def test_missing_required_arg_is_recorded_not_propagated():
    """A malformed action must not abort the actions that follow it.

    Regression: block handlers subscript required args directly, and the
    executor's catch tuple omitted LookupError, so a missing key escaped
    ``raise_on_error=False`` and tore down the rest of the script.
    """
    ex = Executor()
    record = ex.execute_action([
        ["AC_set_var", {"value": 1}],                    # missing "name"
        ["AC_set_var", {"name": "later", "value": 2}],   # must still run
    ], raise_on_error=False)
    assert ex.variables.get_value("later") == 2
    assert any("KeyError" in repr(v) for v in record.values())


def test_ac_try_can_catch_a_missing_required_arg(executor_try):
    """AC_try's catchable set must match the executor's."""
    ex, state = executor_try
    ex.execute_action([["AC_try", {
        "body": [["AC_set_var", {"value": 1}]],   # KeyError: no "name"
        "catch": [["AC_recover"]],
    }]])
    assert state["log"] == ["recover"]


def test_parallel_accepts_valid_branches():
    """Guard: ``branches`` is a list of action lists, one level deeper than
    ``body``. Validating it as a flat list would reject every valid action."""
    ex = Executor()
    record = ex.execute_action([["AC_parallel", {"branches": [
        [["AC_set_var", {"name": "a", "value": 1}]],
        [["AC_set_var", {"name": "b", "value": 2}]],
    ]}]], raise_on_error=True)
    assert record[next(iter(record))]["branches"] == 2


def test_parallel_surfaces_a_failed_branch():
    """A crashed branch must be distinguishable from one returning None.

    Regression: branches ran on bare threads with no exception handling, so a
    failure left ``results[i] = None`` and was reported as success, with the
    traceback going only to stderr.
    """
    ex = Executor()
    with pytest.raises(AutoControlActionException, match="branch"):
        ex.execute_action([["AC_parallel", {"branches": [
            [["AC_set_var", {"name": "a", "value": 1}]],
            [],                                   # empty branch raises in-thread
        ]}]], raise_on_error=True)


@pytest.mark.parametrize("action", [
    ["AC_parallel", {"branches": [[[]]]}],
    ["AC_define_macro", {"name": "m", "body": [[]]}],
    ["AC_for_each_row", {"source": "x.csv", "body": [[]]}],
    ["AC_assert_duration", {"body": [[]]}],
])
def test_nested_bodies_of_every_flow_command_are_validated(action):
    """Commands running nested bodies must have those bodies validated.

    Regression: four commands were missing from the schema map, so their
    bodies were validated by nobody and a malformed nested action surfaced as
    a raw IndexError at dispatch instead of a clean rejection.

    Matching the message matters: AC_for_each_row would otherwise raise for an
    unrelated reason (its ``source`` not existing) and pass without ever
    validating the body.
    """
    ex = Executor()
    with pytest.raises(AutoControlActionException,
                       match=r"must be \[name\] or \[name, params\]"):
        ex.execute_action([action], raise_on_error=True)


def test_ac_try_reraise_propagates_after_finally(executor_try):
    ex, state = executor_try
    result = ex.execute_action([["AC_try", {
        "body": [["AC_boom"]],
        "catch": [["AC_recover"]],
        "finally": [["AC_cleanup"]],
        "reraise": True,
    }]])
    # reraised error is captured in the record (raise_on_error defaults off)
    assert state["log"] == ["recover", "cleanup"]
    assert any("boom" in repr(v) for v in result.values())


def test_ac_try_finally_runs_even_without_catch(executor_try):
    ex, state = executor_try
    ex.execute_action([["AC_try", {
        "body": [["AC_boom"]],
        "finally": [["AC_cleanup"]],
    }]])
    assert state["log"] == ["cleanup"]


def test_ac_try_break_propagates_through_try(executor_try):
    """A loop break inside a try body still stops the enclosing loop."""
    ex, state = executor_try
    ex.execute_action([["AC_loop", {
        "times": 5,
        "body": [["AC_try", {
            "body": [["AC_break"]],
            "finally": [["AC_cleanup"]],
        }]],
    }]])
    # finally ran once, then break stopped the loop after one iteration
    assert state["log"] == ["cleanup"]


def test_ac_try_schema_validates_nested_bodies(executor_try):
    ex, _ = executor_try
    with pytest.raises(AutoControlActionException):
        ex.execute_action([["AC_try", {
            "body": [["AC_nonexistent"]],
        }]])


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
