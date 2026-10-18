"""Journal controls survive nested roots, workers, cancellation and path changes."""
import asyncio
import threading

import pytest

import je_auto_control as ac
from je_auto_control.utils.action_journal.capture import current_journal
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy


def test_options_keep_isolation_and_observe_durable_completions(tmp_path):
    path = tmp_path / "events.jsonl"
    statuses = []
    def observe(status):
        if status != "incomplete":
            assert ac.read_events(path)[-1].status == status
        statuses.append(status)
    variables = {"message": "before"}
    options = ac.JournalRunOptions(variables=variables, run_id="observed", observer=observe)
    result = ac.execute_journal_run([["AC_set_var", {"name": "message", "value": "after"}]], path,
                                    options=options)
    assert statuses == ["incomplete", "ok"] and result["run_id"] == "observed"
    assert variables == {"message": "before"} and current_journal() is None


@pytest.mark.parametrize("worker", ["loop", "parallel", "dag", "capture"])
def test_nested_steps_inherit_observers_and_policies(tmp_path, worker):
    statuses = []
    lock = threading.Lock()
    def observe(status):
        with lock:
            statuses.append(status)
    inner = [["AC_set_var", {"name": "x", "value": 1}]]
    if worker == "loop":
        action = ["AC_loop", {"times": 1, "body": inner}]
    elif worker == "parallel":
        action = ["AC_parallel", {"branches": [inner]}]
    elif worker == "dag":
        action = ["AC_run_dag", {"definition": {"nodes": [{"id": "one", "actions": inner}]}}]
    else:
        action = ["AC_journal_capture", {"path": str(tmp_path / "nested.jsonl"), "body": inner}]
    options = ac.JournalRunOptions(observer=observe, path_policy=PathPolicy([tmp_path]))
    ac.execute_journal_run([action], tmp_path / "outer.jsonl", options=options)
    assert statuses.count("incomplete") == statuses.count("ok") == 2
    assert current_journal() is None


def test_cancellation_before_dispatch_opens_no_file(tmp_path):
    path = tmp_path / "cancelled.jsonl"
    signal = asyncio.CancelledError("controlled cancellation")
    def observe(_status):
        raise signal
    with pytest.raises(asyncio.CancelledError) as caught:
        ac.execute_journal_run([["AC_set_var", {"name": "x", "value": 1}]], path,
                               options=ac.JournalRunOptions(observer=observe))
    assert caught.value is signal and not path.exists() and current_journal() is None


@pytest.mark.parametrize("signal", [ValueError("original"), KeyboardInterrupt(), asyncio.CancelledError()])
def test_completion_observer_never_replaces_an_existing_failure(tmp_path, monkeypatch, signal):
    def fail():
        raise signal
    def observe(status):
        if status != "incomplete":
            raise RuntimeError("observer unavailable")
    monkeypatch.setitem(executor.event_dict, "AC_observed_failure", fail)
    with pytest.raises(type(signal)) as caught:
        with ac.journal_scope(ac.ActionJournal(tmp_path / "failure.jsonl"), observer=observe):
            executor.execute_action([["AC_observed_failure"]], raise_on_error=True)
    assert caught.value is signal and current_journal() is None


def test_observer_failure_after_success_leaves_a_durable_success(tmp_path):
    path = tmp_path / "completed.jsonl"
    def observe(status):
        if status == "ok":
            raise RuntimeError("observer unavailable")
    with pytest.raises(RuntimeError, match="observer unavailable"):
        ac.execute_journal_run([["AC_set_var", {"name": "x", "value": 1}]], path,
                               options=ac.JournalRunOptions(observer=observe))
    assert [event.status for event in ac.read_events(path)] == ["incomplete", "ok"]


def test_nested_controls_compose_without_relaxing_or_duplicating(tmp_path):
    allowed, outside = tmp_path / "allowed", tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    statuses = []
    observer = statuses.append
    policy = PathPolicy([allowed])
    with ac.journal_scope(ac.ActionJournal(allowed / "outer.jsonl"), observer=observer, path_policy=policy):
        with ac.journal_scope(ac.ActionJournal(allowed / "inner.jsonl"), observer=observer,
                              path_policy=policy) as binding:
            assert len(binding.observers) == len(binding.path_policies) == 1
            executor.execute_action([["AC_set_var", {"name": "x", "value": 1}]])
        with pytest.raises(PathNotAllowedError):
            with ac.journal_scope(ac.ActionJournal(outside / "refused.jsonl"), path_policy=PathPolicy()):
                pytest.fail("nested policy relaxed its enclosing roots")
        with pytest.raises(PathNotAllowedError):
            ac.inspect_journal(outside / "absent.jsonl", path_policy=PathPolicy())
    assert statuses == ["incomplete", "ok"] and list(outside.iterdir()) == []


@pytest.mark.parametrize("worker", ["direct", "parallel", "dag"])
def test_dynamic_nested_journal_paths_cannot_escape_captured_roots(tmp_path, worker):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.jsonl"
    nested = [["AC_journal_capture", {"path": "${destination}", "body": [
        ["AC_set_var", {"name": "x", "value": 1}]]}]]
    actions = nested if worker == "direct" else [["AC_parallel", {"branches": [nested]}]] if worker == "parallel" else [
        ["AC_run_dag", {"definition": {"nodes": [{"id": "one", "actions": nested}]}}]]
    result = ac.execute_journal_run(actions, allowed / "outer.jsonl", options=ac.JournalRunOptions(
        variables={"destination": str(outside)}, path_policy=PathPolicy([allowed])))
    assert not outside.exists()
    if worker == "dag":
        outcome = next(iter(result["record"].values()))
        assert outcome["succeeded"] is False and outcome["nodes"]["one"]["status"] == "failed"
        assert "PathNotAllowedError" in outcome["nodes"]["one"]["error"]
    else:
        assert result["failed_actions"] > 0


def test_policy_revocation_stops_the_next_append(tmp_path):
    allowed, other = tmp_path / "allowed", tmp_path / "other"
    allowed.mkdir()
    other.mkdir()
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([allowed])
    path = allowed / "events.jsonl"
    def observe(status):
        if status == "ok":
            policy.set_client_roots([other])
    with pytest.raises(PathNotAllowedError):
        ac.execute_journal_run([["AC_set_var", {"name": "x", "value": 1}]] * 2, path,
                               options=ac.JournalRunOptions(path_policy=policy, observer=observe))
    assert [event.status for event in ac.read_events(path)] == ["incomplete", "ok"]


def test_completion_policy_failure_preserves_a_pending_hard_signal(tmp_path, monkeypatch):
    allowed, other = tmp_path / "allowed", tmp_path / "other"
    allowed.mkdir()
    other.mkdir()
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([allowed])
    signal = KeyboardInterrupt()
    def fail():
        policy.set_client_roots([other])
        raise signal
    monkeypatch.setitem(executor.event_dict, "AC_policy_interruption", fail)
    path = allowed / "unfinished.jsonl"
    with pytest.raises(KeyboardInterrupt) as caught:
        ac.execute_journal_run([["AC_policy_interruption"]], path, options=ac.JournalRunOptions(path_policy=policy))
    assert caught.value is signal
    assert [event.status for event in ac.read_events(path)] == ["incomplete"]


def test_cancelled_reader_closes_its_file_and_preserves_the_signal(tmp_path, monkeypatch):
    from pathlib import Path
    path = tmp_path / "read.jsonl"
    ac.execute_action_with_journal([["AC_set_var", {"name": "x", "value": 1}]], path)
    opened = []
    original = Path.open
    def track(self, *args, **kwargs):
        handle = original(self, *args, **kwargs)
        opened.append(handle)
        return handle
    signal = asyncio.CancelledError("stop reading")
    def observe(_count):
        raise signal
    monkeypatch.setattr(Path, "open", track)
    with pytest.raises(asyncio.CancelledError) as caught:
        ac.inspect_journal(path, observer=observe)
    assert caught.value is signal and opened and all(handle.closed for handle in opened)


def test_reader_observes_all_validated_records_before_filtering(tmp_path):
    path = tmp_path / "read.jsonl"
    for run_id in ("one", "two"):
        ac.execute_action_with_journal([["AC_set_var", {"name": "x", "value": 1}]], path, run_id=run_id)
    seen = []
    payload = ac.inspect_journal(path, run_id="two", limit=1, observer=seen.append)
    assert seen == [1, 2, 3, 4] and len(payload) == 1 and payload[0]["run_id"] == "two"
