"""Regression tests for the executor flow-control defects of the 2026-09-23 audit.

Nested bodies always ran with ``raise_on_error=False``, so a failure inside a
loop, branch or macro was recorded and swallowed: ``AC_try`` never ran its
``catch``, ``AC_retry`` never retried and a strict caller never saw it.
``AC_try`` / ``AC_retry`` missed ``ArithmeticError`` (and retry ``LookupError``)
and swallowed ``MacroDepthExceeded``; ``AC_execute_action`` expanded a
variable's *value* a second time; the LLM planner let a stray ``AC_break``
escape as a raw exception. Every command here is a probe registered on a
private executor -- nothing touches the real mouse or keyboard.
"""
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.executor.action_executor import Executor


@pytest.fixture
def run():
    executor = Executor()
    calls = []

    def probe(tag="", fail=None):
        calls.append(tag)
        errors = {"action": AutoControlActionException("boom"), "zero": ZeroDivisionError("x"),
                  "key": KeyError("x")}
        if fail:
            raise errors[fail]
        return tag

    executor.event_dict["AC_probe"] = probe

    def _run(actions, **kwargs):
        record = executor.execute_action(actions, **kwargs)
        return record, calls

    _run.executor = executor
    return _run


def _probe(tag, fail=None):
    return ["AC_probe", {"tag": tag, **({"fail": fail} if fail else {})}]


def test_try_catches_a_failure_nested_in_a_branch(run):
    _, calls = run([["AC_set_var", {"name": "x", "value": 1}],
                    ["AC_try", {"body": [["AC_if_var", {"name": "x", "op": "eq", "value": 1,
                                                        "then": [_probe("inner", "action")]}],
                                         _probe("after_inner")],
                                "catch": [_probe("CATCH")]}]])
    assert calls == ["inner", "CATCH"]


def test_try_catches_a_failure_nested_in_a_loop(run):
    _, calls = run([["AC_try", {"body": [["AC_loop", {"times": 3, "body": [_probe("l", "action")]}]],
                                "catch": [_probe("CATCH")]}]])
    assert calls == ["l", "CATCH"]


def test_retry_retries_a_failure_nested_in_a_loop(run):
    run([["AC_retry", {"max_attempts": 3, "backoff": 0,
                       "body": [["AC_loop", {"times": 1, "body": [_probe("t", "action")]}]]}]])
    assert run([_probe("end")])[1] == ["t", "t", "t", "end"]


def test_a_strict_run_raises_from_inside_a_loop(run):
    with pytest.raises(AutoControlActionException):
        run([["AC_loop", {"times": 2, "body": [_probe("l", "action")]}], _probe("after")],
            raise_on_error=True)


def test_a_lenient_run_still_records_and_continues(run):
    _, calls = run([["AC_loop", {"times": 2, "body": [_probe("l", "action")]}], _probe("after")])
    assert calls == ["l", "l", "after"]


def test_try_catches_arithmetic_errors(run):
    _, calls = run([["AC_try", {"body": [_probe("b", "zero")], "catch": [_probe("CATCH")]}]])
    assert calls == ["b", "CATCH"]


@pytest.mark.parametrize("fail", ["zero", "key"])
def test_retry_retries_arithmetic_and_lookup_errors(run, fail):
    _, calls = run([["AC_retry", {"max_attempts": 3, "backoff": 0, "body": [_probe("r", fail)]}]])
    assert calls == ["r", "r", "r"]


def test_try_does_not_swallow_the_macro_depth_limit(run):
    record, _ = run([["AC_define_macro", {"name": "rec", "body": [
                        ["AC_try", {"body": [["AC_call_macro", {"name": "rec"}]], "catch": []}]]}],
                     ["AC_call_macro", {"name": "rec"}]])
    assert "MacroDepthExceeded" in str(record)


def test_a_variable_value_is_not_expanded_again_by_execute_action(run):
    run.executor.variables.set("secretish", "TOPSECRET")
    run.executor.variables.set("user_text", "${secretish}")
    _, calls = run([["AC_execute_action", {"action_list": [_probe("${user_text}")]}]])
    assert calls == ["${secretish}"]


def test_execute_action_still_expands_placeholders_once(run):
    run.executor.variables.set("name", "ann")
    _, calls = run([["AC_execute_action", {"action_list": [_probe("${name}")]}]])
    assert calls == ["ann"]


def test_a_planned_break_is_recorded_not_raised(run, monkeypatch):
    from je_auto_control.utils.llm import planner
    monkeypatch.setattr(planner, "plan_actions", lambda *a, **k: [_probe("a"), ["AC_break"], _probe("b")])
    result = planner.run_from_description("x", executor=run.executor)
    assert "outside a loop" in str(result["record"])
