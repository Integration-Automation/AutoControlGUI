"""Explicit manual owners preserve results, signals, counters and journal provenance."""
import asyncio
from concurrent.futures import CancelledError
import os
from pathlib import Path
import subprocess
import sys

import pytest

import je_auto_control as ac
from je_auto_control.utils.run_history import manual as manual_module
from je_auto_control.utils.run_history.context import HistoryBinding, bound_history, current_history
from je_auto_control.utils.run_history.history_store import HistoryStoreError
from je_auto_control.utils.executor.action_executor import executor, recorded_failures
from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
from je_auto_control.utils.mcp_server.context import OperationCancelledError
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.script_vars.execution import execution_scope


@pytest.fixture
def store(tmp_path):
    value = ac.HistoryStore(tmp_path / "history.sqlite")
    yield value
    value.close()


def test_scope_preserves_existing_variables_results_and_owner(store):
    assert ac.manual_history_scope is manual_module.manual_history_scope
    with execution_scope({"message": "before"}):
        with ac.manual_history_scope(store=store, source_id="editor", script_path="<editor>") as binding:
            assert isinstance(binding, ac.HistoryBinding) and current_history() is binding
            result = executor.execute_action([["AC_set_var", {"name": "message", "value": "after"}]])
        assert executor.variables.get("message") == "after" and result
    row = store.get_run(binding.run_id)
    assert row.source_type == "manual" and row.source_id == "editor" and row.script_path == "<editor>"
    assert row.status == "ok" and row.finished_at is not None and row.artifact_path is None
    assert current_history() is None


def test_scope_counts_only_its_own_soft_failures(store, monkeypatch):
    def fail():
        raise ValueError("controlled failure")
    monkeypatch.setitem(executor.event_dict, "AC_manual_failure", fail)
    executor.execute_action([["AC_manual_failure"]])
    before = recorded_failures()
    with ac.manual_history_scope(store=store) as clean:
        executor.execute_action([["AC_set_var", {"name": "x", "value": 1}]])
    assert store.get_run(clean.run_id).status == "ok" and recorded_failures() == before
    with ac.manual_history_scope(store=store) as failed:
        result = executor.execute_action([["AC_manual_failure"]])
    assert any("controlled failure" in str(value) for value in result.values())
    assert store.get_run(failed.run_id).status == "error"
    assert recorded_failures() == before + 1


_SIGNALS = [ValueError("original"), KeyboardInterrupt(), SystemExit(7), GeneratorExit(),
            asyncio.CancelledError(), CancelledError(), OperationCancelledError("cancelled")]


@pytest.mark.parametrize("signal", _SIGNALS, ids=lambda signal: type(signal).__name__)
def test_original_signal_is_retained_and_history_is_error(store, signal):
    with pytest.raises(type(signal)) as caught:
        with ac.manual_history_scope(store=store) as binding:
            raise signal
    assert caught.value is signal and current_history() is None
    assert store.get_run(binding.run_id).status == "error"


@pytest.mark.parametrize("signal", _SIGNALS, ids=lambda signal: type(signal).__name__)
def test_failed_completion_does_not_replace_pending_signal(store, monkeypatch, signal):
    def fail(*args, **kwargs):
        raise HistoryStoreError("completion unavailable")
    monkeypatch.setattr(store, "finish_run", fail)
    with pytest.raises(type(signal)) as caught:
        with ac.manual_history_scope(store=store) as binding:
            raise signal
    assert caught.value is signal and store.get_run(binding.run_id).status == "running"


def test_failed_completion_without_original_signal_propagates(store, monkeypatch):
    monkeypatch.setattr(store, "finish_run", lambda *a, **k: False)
    with pytest.raises(HistoryStoreError, match="missing"):
        with ac.manual_history_scope(store=store):
            pass


def test_start_failure_has_no_body_effect_and_restores_parent(store, monkeypatch):
    parent = HistoryBinding(store, store.start_run("manual", "parent", "script"))
    def fail(*args, **kwargs):
        raise HistoryStoreError("start unavailable")
    monkeypatch.setattr(store, "start_run", fail)
    with bound_history(parent):
        with pytest.raises(HistoryStoreError):
            with ac.manual_history_scope(store=store):
                pytest.fail("body executed after failed start")
        assert current_history() is parent


def test_nested_owners_restore_and_both_observe_body_failure(store, monkeypatch):
    def fail():
        raise ValueError("controlled")
    monkeypatch.setitem(executor.event_dict, "AC_manual_failure", fail)
    with ac.manual_history_scope(store=store, source_id="outer") as outer:
        with ac.manual_history_scope(store=store, source_id="inner") as inner:
            executor.execute_action([["AC_manual_failure"]])
        assert current_history() is outer
    assert outer.run_id != inner.run_id
    assert [store.get_run(owner.run_id).status for owner in (outer, inner)] == ["error", "error"]


@pytest.mark.parametrize("order", ["history-first", "journal-first"])
def test_existing_and_new_journals_are_linked(store, tmp_path, order):
    path = tmp_path / "events.jsonl"
    if order == "history-first":
        with ac.manual_history_scope(store=store) as owner:
            ac.execute_journal_run([["AC_set_var", {"name": "x", "value": 1}]], path,
                                   options=ac.JournalRunOptions(run_id="journal"))
    else:
        with ac.journal_scope(ac.ActionJournal(path), run_id="journal"):
            with ac.manual_history_scope(store=store) as owner:
                executor.execute_action([["AC_set_var", {"name": "x", "value": 1}]])
    assert store.journals_for_run(owner.run_id) == [ac.JournalLink(owner.run_id, str(path.resolve()), "journal")]
    assert len(ac.read_events(path)) == 2
    store.clear()
    assert path.exists()


@pytest.mark.parametrize("worker", ["parallel", "dag"])
def test_worker_captures_link_to_the_manual_owner(store, tmp_path, worker):
    path = tmp_path / "worker.jsonl"
    body = [["AC_journal_capture", {"path": str(path), "body": [["AC_set_var", {"name": "x", "value": 1}]]}]]
    if worker == "parallel":
        actions = [["AC_parallel", {"branches": [body]}]]
    else:
        actions = [["AC_run_dag", {"definition": {"nodes": [{"id": "one", "actions": body}]}}]]
    with ac.manual_history_scope(store=store) as owner:
        executor.execute_action(actions, raise_on_error=True)
    assert len(store.journals_for_run(owner.run_id)) == 1 and path.exists()


def test_metadata_and_failure_text_are_masked_before_sqlite(store):
    secret = "manual-private-marker"
    with secret_log_scope():
        remember_secret(secret)
        with pytest.raises(ValueError):
            with ac.manual_history_scope(store=store, source_id=secret, script_path=secret) as owner:
                raise ValueError(secret)
    row = store.get_run(owner.run_id)
    assert row.source_id == row.script_path == "***" and secret not in row.error_text


def test_ambient_journal_policy_is_checked_before_linking(store, tmp_path):
    policy = ac.PathPolicy(use_client_roots=True)
    policy.set_client_roots([tmp_path])
    with ac.journal_scope(ac.ActionJournal(tmp_path / "events.jsonl"), path_policy=policy):
        policy.set_client_roots([tmp_path / "elsewhere"])
        with pytest.raises(ac.PathNotAllowedError):
            with ac.manual_history_scope(store=store):
                pytest.fail("body executed outside active roots")
    assert store.list_runs()[0].status == "error" and store.journals_for_run(store.list_runs()[0].id) == []


def test_viewer_is_refused_before_store_effects(store, monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("viewer created history")
    monkeypatch.setattr(store, "start_run", fail)
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        with pytest.raises(ac.AuthorizationError):
            with ac.manual_history_scope(store=store):
                pass


def test_import_without_sqlite_or_qt_opens_no_database(tmp_path):
    probe = """
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'sqlite3', 'PySide6'}:
            raise ImportError('blocked for controlled import')
sys.meta_path.insert(0, Block())
import je_auto_control as ac
assert callable(ac.manual_history_scope)
assert not any(name.startswith(('sqlite3', 'PySide6')) for name in sys.modules)
print('ok')
"""
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120,
                          env=dict(os.environ, PYTHONPATH=str(Path.cwd())), check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"


def test_existing_journal_secret_metadata_is_refused_before_link(store, tmp_path):
    secret = "manual-secret-path"
    with secret_log_scope():
        with ac.journal_scope(ac.ActionJournal(tmp_path / (secret + ".jsonl")), run_id="ambient"):
            remember_secret(secret)
            with pytest.raises(HistoryStoreError, match="resolved secret"):
                with ac.manual_history_scope(store=store):
                    pytest.fail("unsafe provenance reached body")
    row = store.list_runs()[0]
    assert row.status == "error" and store.journals_for_run(row.id) == []
    assert secret not in row.error_text


@pytest.mark.parametrize("field,value", [("source_id", ""), ("source_id", None), ("script_path", "")])
def test_invalid_labels_have_no_store_effects(store, field, value):
    with pytest.raises(HistoryStoreError):
        with ac.manual_history_scope(store=store, **{field: value}):
            pytest.fail("invalid labels executed")
    assert store._conn is None


def test_error_formatting_does_not_replace_the_original_failure(store):
    class BrokenError(ac.AutoControlException):
        def __repr__(self):
            raise ValueError("failed to format error")
    original = BrokenError("original")
    with pytest.raises(BrokenError) as caught:
        with ac.manual_history_scope(store=store) as owner:
            raise original
    assert caught.value is original and store.get_run(owner.run_id).status == "error"


def test_public_binding_annotations_resolve_at_runtime():
    from typing import get_type_hints
    assert get_type_hints(ac.HistoryBinding)["store"] is ac.HistoryStore
