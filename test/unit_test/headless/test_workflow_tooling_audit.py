"""Workflow / test-tooling defects from the 2026-09-24 audit.

Merged shard reports lost errored cases and every case; a seeded date moved
day by day; smart waits slept past their deadline; ``window=0`` divided by
zero; unknown hit policies were accepted and ANY did not check agreement; a
non-callable state-machine predicate always fired and StateMachineError was
outside the framework family; assert_poll raised a non-assertion; soft
assertion failures vanished when the block raised; repeated debugger steps
overwrote each other; overlapping repeats were counted; a loop guard could be
built that never trips; DeterministicRun left numpy seeded.
"""
import time

import pytest

from je_auto_control.utils.decision_table.decision_table import evaluate_table
from je_auto_control.utils.deterministic.deterministic import DeterministicRun
from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException, AutoControlException,
)
from je_auto_control.utils.expect_poll.expect_poll import assert_poll
from je_auto_control.utils.flow_debugger.flow_debugger import FlowDebugger
from je_auto_control.utils.loop_guard.loop_guard import LoopGuard
from je_auto_control.utils.process_mining.process_mining import find_repeated_sequences
from je_auto_control.utils.smart_waits.waits import wait_until_window_closed
from je_auto_control.utils.soft_assert.soft_assert import SoftAssertions
from je_auto_control.utils.state_machine.engine import StateMachine, StateMachineError
from je_auto_control.utils.test_data.test_data import generate_rows
from je_auto_control.utils.test_shard.test_shard import merge_results, shard_flows
from je_auto_control.utils.test_suite import result as suite_result


def test_merged_suite_reports_keep_errors_and_cases():
    report = suite_result.TestSuiteResult("s", [
        suite_result.TestCaseResult("c", "error"),
        suite_result.TestCaseResult("d", "failed")]).to_dict()
    merged = merge_results([report])
    assert merged["errors"] == merged["errored"] == 1
    assert len(merged["cases"]) == 2


def test_a_seeded_date_does_not_depend_on_today():
    rows = generate_rows({"d": "date"}, 3, seed=7)
    assert all(row["d"] <= "2030-12-31" for row in rows)
    assert rows == generate_rows({"d": "date"}, 3, seed=7)


def test_a_wait_does_not_sleep_past_its_deadline():
    started = time.monotonic()
    wait_until_window_closed("x", timeout_s=0.1, poll_interval_s=1.5,
                             finder=lambda title, case: True)
    assert time.monotonic() - started < 1.0


def test_a_zero_window_is_a_value_error():
    with pytest.raises(ValueError):
        shard_flows(["a", "b"], 2, window=0)


def _table(policy):
    return {"hit_policy": policy, "rules": [
        {"conditions": {"x": 1}, "outputs": {"y": "a"}},
        {"conditions": {"x": 1}, "outputs": {"y": "b"}}]}


def test_hit_policies_are_validated_and_any_must_agree():
    with pytest.raises(ValueError, match="hit policy"):
        evaluate_table(_table("COLECT"), {"x": 1})
    with pytest.raises(ValueError, match="ANY"):
        evaluate_table(_table("ANY"), {"x": 1})
    agreeing = {"hit_policy": "ANY", "rules": [
        {"conditions": {"x": 1}, "outputs": {"y": "a"}},
        {"conditions": {"x": 1}, "outputs": {"y": "a"}}]}
    assert evaluate_table(agreeing, {"x": 1}) == {"y": "a"}


def test_a_string_predicate_is_a_spec_error():
    spec = {"initial": "a", "max_steps": 3, "states": {
        "a": {"transitions": [{"predicate": "ctx.ok == True", "go_to": "b"}]},
        "b": {"final": True}}}
    with pytest.raises(StateMachineError, match="callable"):
        StateMachine(spec, execute_action=lambda action: None).run()
    assert issubclass(StateMachineError, AutoControlException)


def test_assert_poll_raises_an_assertion():
    with pytest.raises(AutoControlAssertionException):
        assert_poll(lambda: 0, lambda value: value == 1, timeout_s=0.05, interval_s=0.01)


def test_soft_failures_survive_an_exception_in_the_block():
    if not hasattr(BaseException, "add_note"):
        pytest.skip("exception notes need Python 3.11")
    with pytest.raises(ValueError) as info:
        with SoftAssertions() as soft:
            soft.check(False, "first check")
            raise ValueError("boom")
    assert any("first check" in note for note in info.value.__notes__)


class _Exec:
    def execute_action(self, actions):
        return {f"execute: {actions[0]}": "ok"}


def test_repeated_debugger_steps_keep_both_records():
    debugger = FlowDebugger([["AC_x"], ["AC_x"]], executor=_Exec())
    debugger.step()
    debugger.step()
    assert len(debugger.record) == 2


def test_repeats_are_counted_without_overlap():
    patterns = find_repeated_sequences(["A"] * 4, min_len=2, max_len=2, min_count=3)
    assert patterns == []
    patterns = find_repeated_sequences(["A"] * 6, min_len=2, max_len=2, min_count=3)
    assert [p.count for p in patterns] == [3]


def test_a_loop_guard_threshold_must_fit_its_window():
    with pytest.raises(ValueError):
        LoopGuard(critical=25)
    LoopGuard(warn=8, critical=15, window=20)


def test_deterministic_run_restores_numpy():
    numpy = pytest.importorskip("numpy")
    numpy.random.seed(123)
    expected = numpy.random.random()
    numpy.random.seed(123)
    with DeterministicRun(seed=1):
        numpy.random.random()
    assert numpy.random.random() == expected
