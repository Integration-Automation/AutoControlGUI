"""Regression tests for the logic-engine defects of the 2026-09-23 audit.

DAG nodes whose actions failed counted as succeeded, a runner's ``KeyError``
escaped ``run_dag``, and a slow node held back unrelated ready work. The state
machine let unimplemented guards pass, never waited for an ``after`` timer and
failed on reaching the final state on its last step. Recurrence rules gave
wrong YEARLY dates, accepted INTERVAL=0 and never-matching rules, and yielded a
date for count=0. A data-driven suite row variable outlived its case, and an
``OverflowError`` escaped the executor.
"""
import datetime as dt
import threading
import time

import pytest

from je_auto_control.utils.dag.runner import run_dag
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.recurrence.recurrence import occurrences, parse_rrule
from je_auto_control.utils.state_machine.engine import StateMachineError, run_state_machine
from je_auto_control.utils.test_suite.runner import run_suite

_START = dt.datetime(2026, 1, 1, 9)


# --- DAG ----------------------------------------------------------------------

def test_a_node_whose_actions_fail_is_failed_and_its_dependants_skipped():
    result = run_dag({"nodes": [
        {"id": "a", "actions": [["AC_sleep", {"seconds": -1}]]},
        {"id": "b", "actions": [], "depends_on": ["a"]},
    ]})
    assert (result.nodes["a"].status, result.nodes["b"].status) == ("failed", "skipped")


def test_a_runner_key_error_fails_the_node():
    def runner(node, _definition):
        raise KeyError("x")

    result = run_dag({"nodes": [{"id": "a", "actions": []}]}, local_runner=runner)
    assert result.nodes["a"].status == "failed"


def test_a_slow_node_does_not_hold_back_unrelated_ready_work():
    started = {}
    release = threading.Event()

    def runner(node, _definition):
        started[node.id] = time.monotonic()
        if node.id == "a_slow":
            release.wait(2.0)

    thread = threading.Thread(target=lambda: run_dag({"nodes": [
        {"id": "a_slow", "actions": []},
        {"id": "fast", "actions": []},
        {"id": "child", "actions": [], "depends_on": ["fast"]},
    ]}, local_runner=runner, max_parallel=4))
    thread.start()
    deadline = time.monotonic() + 1.0
    while "child" not in started and time.monotonic() < deadline:
        time.sleep(0.01)
    release.set()
    thread.join()
    assert started["child"] - started["fast"] < 0.5, "child waited for the slow node"


# --- state machine ------------------------------------------------------------

def _machine(transitions, **extra):
    return {"initial": "s", "states": {"s": {"transitions": transitions},
                                       "done": {"final": True}}, **extra}


def test_an_unimplemented_guard_is_an_error_not_a_pass():
    with pytest.raises(StateMachineError, match="unknown guard"):
        run_state_machine(_machine([{"if_pixel": [1, 2], "go_to": "done"}]),
                          execute_action=lambda action: None)


def test_if_image_found_fires_only_once_the_image_is_on_screen(monkeypatch):
    from je_auto_control.utils.exception.exceptions import ImageNotFoundException
    from je_auto_control.wrapper import auto_control_image
    polls = []

    def locate(image, **_kwargs):
        polls.append(image)
        if len(polls) < 3:
            raise ImageNotFoundException("not yet")
        return (10, 10)

    monkeypatch.setattr(auto_control_image, "locate_image_center", locate)
    spec = _machine([{"if_image_found": "welcome.png", "go_to": "done"},
                     {"after": 5, "go_to": "s"}])
    assert run_state_machine(spec, execute_action=lambda action: None)["final_state"] == "done"
    assert polls[-1] == "welcome.png" and len(polls) == 3


def test_an_after_guard_waits_for_its_timer():
    result = run_state_machine(_machine([{"after": 0.2, "go_to": "done"}]),
                               execute_action=lambda action: None)
    assert result["final_state"] == "done"
    assert result["elapsed_s"] >= 0.2


def test_reaching_the_final_state_on_the_last_step_succeeds():
    result = run_state_machine(_machine([{"go_to": "done"}], max_steps=1),
                               execute_action=lambda action: None)
    assert result == {"final_state": "done", "steps": 1, "elapsed_s": result["elapsed_s"]}


# --- recurrence ---------------------------------------------------------------

def _dates(rule, count=3):
    return [str(moment.date()) for moment in occurrences(parse_rrule(rule), _START, count=count)]


def test_yearly_byday_ordinal_counts_within_the_year():
    assert _dates("FREQ=YEARLY;BYDAY=-1FR", 2) == ["2026-12-25", "2027-12-31"]
    assert _dates("FREQ=YEARLY;BYDAY=20MO", 1) == ["2026-05-18"]


def test_yearly_bymonthday_without_bymonth_covers_every_month():
    dates = _dates("FREQ=YEARLY;BYMONTHDAY=1", 13)
    assert dates[:12] == [f"2026-{month:02d}-01" for month in range(1, 13)]


def test_a_rule_that_can_never_match_ends():
    assert list(occurrences(parse_rrule("FREQ=MONTHLY;BYMONTH=2;BYMONTHDAY=30"), _START)) == []


@pytest.mark.parametrize("rule", ["FREQ=DAILY;INTERVAL=0", "FREQ=DAILY;INTERVAL=x",
                                  "FREQ=DAILY;COUNT=0", "FREQ=YEARLY;BYMONTH=13",
                                  "FREQ=MONTHLY;BYMONTHDAY=40"])
def test_invalid_rule_parts_are_rejected(rule):
    with pytest.raises(AutoControlException):
        parse_rrule(rule)


def test_count_zero_yields_nothing():
    assert list(occurrences(parse_rrule("FREQ=DAILY"), _START, count=0)) == []


# --- suite runner / executor ---------------------------------------------------

def test_a_row_variable_does_not_outlive_its_case():
    executor = Executor()
    run_suite({"name": "s", "cases": [
        {"name": "rows", "data": {"kind": "inline", "rows": [{"u": "a"}, {"u": "b"}]},
         "actions": [["AC_set_var", {"name": "seen", "value": "${row.u}"}]]},
    ]}, executor=executor, respect_quarantine=False)
    assert "row" not in executor.variables


def test_an_overflow_error_is_contained_by_the_executor():
    executor = Executor()

    def overflow():
        raise OverflowError("date value out of range")

    executor.event_dict["AC_overflow"] = overflow
    executor.execute_action([["AC_overflow"], ["AC_set_var", {"name": "after", "value": 1}]],
                            _validated=True)
    assert executor.variables.get_value("after") == 1
