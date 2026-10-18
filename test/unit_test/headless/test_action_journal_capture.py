"""Executor capture preserves real outcomes, parent links and run isolation."""
import subprocess
import sys

import pytest

from je_auto_control.utils.action_journal import ActionJournal, execute_action_with_journal, journal_scope, read_events
from je_auto_control.utils.action_journal.capture import current_journal
from je_auto_control.utils.action_journal.events import ActionJournalError
from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.script_vars.execution import execution_scope

PROBE = "AC_journal_probe"


@pytest.fixture
def seen(monkeypatch):
    values = []
    monkeypatch.setitem(executor.event_dict, PROBE, lambda value: values.append(value) or value)
    return values


def _completed(path):
    return [event for event in read_events(path) if event.status != "incomplete"]


def test_scoped_capture_preserves_source_refs_and_never_writes_resolved_secrets(tmp_path, seen, monkeypatch):
    from je_auto_control.utils.secrets import default_secret_manager
    monkeypatch.setattr(default_secret_manager, "get", lambda name: "resolved-private-value")
    path = tmp_path / "events.jsonl"
    result = execute_action_with_journal([[PROBE, {"value": "${secrets.LOGIN}"}]], path, run_id="run")
    assert result["run_id"] == "run" and result["failed_actions"] == 0
    assert seen == ["resolved-private-value"]
    assert "resolved-private-value" not in path.read_text(encoding="utf-8")
    events = read_events(path)
    assert [event.status for event in events] == ["incomplete", "ok"]
    assert all(event.parameters == {"value": "${secrets.LOGIN}"} for event in events)
    assert events[-1].outcome_type == "text"
    assert current_journal() is None


def test_loop_children_share_run_and_point_to_the_observed_parent(tmp_path, seen):
    path = tmp_path / "events.jsonl"
    execute_action_with_journal([["AC_loop", {"times": 2, "body": [[PROBE, {"value": "child"}]]}]],
                                path, run_id="loop")
    completed = _completed(path)
    parent = next(event for event in completed if event.command == "AC_loop")
    children = [event for event in completed if event.command == PROBE]
    assert len(children) == 2 and len({event.step_id for event in children}) == 2
    assert all(event.run_id == "loop" and event.parent_id == parent.step_id for event in children)
    assert parent.parent_id is None and parent.status == "ok" and seen == ["child", "child"]
    assert all(event.sequence < parent.sequence for event in children)


@pytest.mark.parametrize("block", ["parallel", "dag"])
def test_worker_actions_retain_parent_and_identity(tmp_path, seen, block):
    path = tmp_path / "events.jsonl"
    actions = [[[PROBE, {"value": value}]] for value in ("left", "right")]
    if block == "parallel":
        parent_command = "AC_parallel"
        script = [[parent_command, {"branches": actions}]]
    else:
        parent_command = "AC_run_dag"
        script = [[parent_command, {"definition": {"nodes": [
            {"id": str(index), "actions": body} for index, body in enumerate(actions)]}}]]
    execute_action_with_journal(script, path, run_id="workers", device_id="device", session_id="session")
    completed = _completed(path)
    parent = next(event for event in completed if event.command == parent_command)
    children = [event for event in completed if event.command == PROBE]
    assert sorted(seen) == ["left", "right"] and len(children) == 2
    assert all(event.parent_id == parent.step_id for event in children)
    assert all((event.run_id, event.device_id, event.session_id) == ("workers", "device", "session")
               for event in read_events(path))


@pytest.mark.parametrize("strict", [False, True])
def test_failed_dispatch_is_never_reported_as_success(tmp_path, monkeypatch, strict):
    def fail():
        raise AutoControlActionException("private exception payload")

    monkeypatch.setitem(executor.event_dict, "AC_journal_fail", fail)
    path = tmp_path / "events.jsonl"
    with journal_scope(ActionJournal(path), run_id="failure"):
        if strict:
            with pytest.raises(AutoControlActionException):
                executor.execute_action([["AC_journal_fail"]], raise_on_error=True)
        else:
            executor.execute_action([["AC_journal_fail"]])
    assert _completed(path)[0].status == "error"
    assert "private exception payload" not in path.read_text(encoding="utf-8")
    assert current_journal() is None


@pytest.mark.parametrize("nested,status", [(False, "error"), (True, "ok")])
def test_break_records_its_actual_control_flow_outcome(tmp_path, nested, status):
    path = tmp_path / "events.jsonl"
    actions = [["AC_break"]]
    if nested:
        actions = [["AC_loop", {"times": 2, "body": actions}]]
    execute_action_with_journal(actions, path)
    assert all(event.status == status for event in _completed(path))


def test_cancellation_is_recorded_and_restores_context(tmp_path, monkeypatch):
    def cancel():
        raise KeyboardInterrupt()

    monkeypatch.setitem(executor.event_dict, "AC_journal_cancel", cancel)
    path = tmp_path / "events.jsonl"
    with pytest.raises(KeyboardInterrupt):
        execute_action_with_journal([["AC_journal_cancel"]], path)
    assert _completed(path)[0].status == "cancelled"
    assert current_journal() is None


def test_dry_run_is_labelled_and_invokes_no_handler(tmp_path, seen):
    path = tmp_path / "events.jsonl"
    execute_action_with_journal([[PROBE, {"value": "never"}]], path, dry_run=True)
    event = _completed(path)[0]
    assert event.status == "dry_run" and "not_executed" in event.non_replayable
    assert seen == []


def test_nested_scopes_restore_parent_and_isolate_seeded_variables(tmp_path, seen):
    outer, inner = tmp_path / "outer.jsonl", tmp_path / "inner.jsonl"
    with execution_scope({"owner": "outer"}):
        with journal_scope(ActionJournal(outer), run_id="outer") as binding:
            execute_action_with_journal([[PROBE, {"value": "${owner}"}]], inner,
                                        variables={"owner": "inner"}, run_id="inner")
            assert current_journal() is binding
            executor.execute_action([[PROBE, {"value": "${owner}"}]])
    assert seen == ["inner", "outer"] and current_journal() is None
    assert {event.run_id for event in read_events(outer)} == {"outer"}
    assert {event.run_id for event in read_events(inner)} == {"inner"}


def test_plain_execution_keeps_its_existing_result_contract(tmp_path, seen):
    record = executor.execute_action([[PROBE, {"value": "plain"}]])
    assert list(record.values()) == ["plain"] and seen == ["plain"]
    assert list(tmp_path.iterdir()) == [] and current_journal() is None


@pytest.mark.parametrize("strict", [False, True])
def test_completion_storage_failure_keeps_the_durable_start_incomplete(tmp_path, monkeypatch, strict):
    def fail():
        raise AutoControlActionException("original failure")

    monkeypatch.setitem(executor.event_dict, "AC_journal_fail", fail)
    journal = ActionJournal(tmp_path / "events.jsonl")
    append = journal.append
    calls = []

    def interrupted(event):
        calls.append(event.status)
        if len(calls) > 1:
            raise ActionJournalError("storage unavailable")
        append(event)

    monkeypatch.setattr(journal, "append", interrupted)
    with pytest.raises(AutoControlActionException if strict else ActionJournalError):
        with journal_scope(journal):
            executor.execute_action([["AC_journal_fail"]], raise_on_error=strict)
    assert [event.status for event in read_events(journal.path)] == ["incomplete"]
    assert current_journal() is None


def test_pre_dispatch_callback_cancellation_does_not_invent_an_attempt(tmp_path, seen):
    path = tmp_path / "events.jsonl"

    def stopped(_action):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        with journal_scope(ActionJournal(path)):
            executor.execute_action([[PROBE, {"value": "never"}]], step_callback=stopped)
    assert not path.exists() and seen == [] and current_journal() is None


def test_process_exit_during_a_command_preserves_only_its_incomplete_start(tmp_path):
    path = tmp_path / "crash.jsonl"
    script = '''
import os, sys
from pathlib import Path
from je_auto_control.utils.action_journal import ActionJournal, journal_scope
from je_auto_control.utils.executor.action_executor import executor
executor.event_dict["AC_journal_crash"] = lambda: os._exit(23)
with journal_scope(ActionJournal(Path(sys.argv[1])), run_id="crashed"):
    executor.execute_action([["AC_journal_crash"]])
'''
    done = subprocess.run(  # nosec B603  # nosemgrep  # reason: own fixed helper, only a temp path is passed as data
        [sys.executable, "-c", script, str(path)], capture_output=True, text=True, timeout=60, check=False,
    )
    assert done.returncode == 23, done.stderr
    events = read_events(path)
    assert len(events) == 1 and events[0].run_id == "crashed" and events[0].status == "incomplete"
