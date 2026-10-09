"""Steps a runner hands to a thread pool keep the block that ran them as parent.

The DAG runner, the device matrix and the bulkhead used to record their steps
with ``parent_id`` ``None``; candidate generation then guessed the nesting from
timestamps and dropped the steps as ``detached``.
"""
import pytest

from je_auto_control.utils.action_journal import recorder
from je_auto_control.utils.action_journal.store import read_events
from je_auto_control.utils.codegen.journal_import import generate_candidate_from_log
from je_auto_control.utils.executor.action_executor import Executor


@pytest.fixture(autouse=True)
def _journal_off():
    recorder.stop_action_journal()
    yield
    recorder.stop_action_journal()


@pytest.fixture
def fake_executor():
    executor = Executor()
    executor.event_dict["AC_fake_step"] = lambda **kwargs: kwargs.get("n", 0)
    return executor


def _run(tmp_path, executor, actions):
    journal = tmp_path / "journal.jsonl"
    recorder.start_action_journal(journal, run_id="run-parents")
    try:
        executor.execute_action(actions, raise_on_error=True)
    finally:
        recorder.stop_action_journal()
    return journal, read_events(journal)


def _one(events, command):
    found = [event for event in events if event.command == command]
    assert len(found) == 1, found
    return found[0]


def test_dag_nodes_name_the_dag_step_as_parent(tmp_path, fake_executor):
    definition = {"nodes": [
        {"id": "a", "actions": [["AC_fake_step", {"n": 1}]]},
        {"id": "b", "actions": [["AC_fake_step", {"n": 2}]], "depends_on": ["a"]},
        {"id": "c", "actions": [["AC_fake_step", {"n": 3}]]},
    ]}
    journal, events = _run(tmp_path, fake_executor, [
        ["AC_run_dag", {"definition": definition, "max_parallel": 2}]])
    dag = _one(events, "AC_run_dag")
    steps = [event for event in events if event.command == "AC_fake_step"]
    assert len(steps) == 3
    assert {event.parent_id for event in steps} == {dag.step_id}
    assert {event.params["n"]: event.branch for event in steps} == {1: 0, 2: 1, 3: 2}
    assert all(event.thread != dag.thread for event in steps)
    candidate = generate_candidate_from_log(journal, run_id="run-parents")
    assert not [step for step in candidate.manifest["steps"] if step["mode"] == "detached"]
    assert not any("another thread" in warning for warning in candidate.warnings)


def test_device_matrix_steps_name_the_matrix_step_as_parent(tmp_path, fake_executor):
    # A fresh executor runs each device, so the body uses a real, inert command.
    journal, events = _run(tmp_path, fake_executor, [
        ["AC_run_device_matrix", {
            "actions": [["AC_set_var", {"name": "seen", "value": 1}]],
            "devices": [{"name": "one"}, {"name": "two"}], "max_parallel": 2}]])
    matrix = _one(events, "AC_run_device_matrix")
    steps = [event for event in events if event.command == "AC_set_var"]
    assert len(steps) == 2
    assert {event.parent_id for event in steps} == {matrix.step_id}
    assert sorted(event.branch for event in steps) == [0, 1]
    candidate = generate_candidate_from_log(journal, run_id="run-parents")
    assert not [step for step in candidate.manifest["steps"] if step["mode"] == "detached"]


def test_bulkhead_body_names_the_bulkhead_step_as_parent(tmp_path, fake_executor):
    _journal, events = _run(tmp_path, fake_executor, [
        ["AC_bulkhead_run", {"name": "journal-parents", "max_concurrent": 1,
                             "actions": [["AC_fake_step", {"n": 1}]]}]])
    bulkhead = _one(events, "AC_bulkhead_run")
    assert _one(events, "AC_fake_step").parent_id == bulkhead.step_id


def test_run_dag_called_from_python_under_a_step_carries_that_step(tmp_path, fake_executor):
    from je_auto_control.utils.dag import run_dag

    def call_dag():
        return run_dag({"nodes": [{"id": "a", "actions": [["AC_fake_step", {"n": 9}]]}]},
                       local_runner=lambda node, _d: fake_executor.execute_action(
                           list(node.actions), raise_on_error=True)).succeeded

    fake_executor.event_dict["AC_fake_host"] = call_dag
    _journal, events = _run(tmp_path, fake_executor, [["AC_fake_host"]])
    assert _one(events, "AC_fake_step").parent_id == _one(events, "AC_fake_host").step_id


def test_a_scope_restores_what_the_thread_had_before():
    with recorder.branch_scope("outer", 4):
        with recorder.branch_scope("inner", 1):
            assert recorder._LOCAL.parent == "inner"
        assert (recorder._LOCAL.parent, recorder._LOCAL.branch) == ("outer", 4)
    assert (recorder._LOCAL.parent, recorder._LOCAL.branch) == (None, None)


def test_carry_step_is_the_function_itself_without_a_journal():
    def work():
        return 1
    assert recorder.carry_step(work, 0) is work
