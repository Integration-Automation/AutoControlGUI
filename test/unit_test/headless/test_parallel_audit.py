"""AC_parallel defects from the 2026-09-24 audit (fake commands only).

Branches run on new threads, where strictness, the macro depth and the
failure count start from scratch: a failing branch under ``raise_on_error``
was only recorded (AC_parallel reported success, AC_try never caught it, the
CLI exit code never saw it), and a macro recursing through a branch was never
stopped. A JSON-string ``branches`` also ran half a branch before its unknown
command was noticed.
"""
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.executor import action_executor
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.flow_control import MAX_MACRO_DEPTH


@pytest.fixture
def ex():
    executor = Executor()
    calls = []

    def fail():
        raise ValueError("boom")

    def count():
        calls.append(1)
        if len(calls) > MAX_MACRO_DEPTH + 20:
            raise RuntimeError("recursion was not bounded")

    executor.event_dict["AC_fake_fail"] = fail
    executor.event_dict["AC_fake_ok"] = lambda: calls.append("ok")
    executor.event_dict["AC_fake_count"] = count
    executor.calls = calls
    return executor


def test_a_failed_branch_raises_under_raise_on_error(ex):
    with pytest.raises(AutoControlActionException, match="branch"):
        ex.execute_action([["AC_parallel", {"branches": [[["AC_fake_fail"]]]}]],
                          raise_on_error=True)


def test_ac_try_catches_a_failed_branch(ex):
    ex.execute_action([["AC_try", {
        "body": [["AC_parallel", {"branches": [[["AC_fake_fail"]]]}]],
        "catch": [["AC_set_var", {"name": "caught", "value": "yes"}]]}]])
    assert ex.variables.get("caught") == "yes"


def test_a_failure_in_a_branch_counts_for_the_caller(ex):
    action_executor.reset_recorded_failures()
    ex.execute_action([["AC_parallel", {"branches": [[["AC_fake_fail"]]]}]])
    assert action_executor.recorded_failures() >= 1


def test_macro_recursion_through_a_branch_is_bounded(ex):
    ex.execute_action([["AC_define_macro", {"name": "m", "body": [
        ["AC_fake_count"],
        ["AC_parallel", {"branches": [[["AC_call_macro", {"name": "m"}]]]}]]}],
        ["AC_call_macro", {"name": "m"}]])
    assert len(ex.calls) <= MAX_MACRO_DEPTH + 1


def test_a_string_branch_is_validated_before_anything_runs(ex):
    ex.execute_action([["AC_parallel", {"branches": '[[["AC_fake_ok"], ["AC_no_such_cmd"]]]'}]])
    assert ex.calls == []
