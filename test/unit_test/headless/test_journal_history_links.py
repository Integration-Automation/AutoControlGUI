"""Journal provenance follows explicit history owners without owning journal files."""
import json
from pathlib import Path

import pytest

from je_auto_control.utils.action_journal import ActionJournal, journal_scope
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.run_history.history_store import (
    HistoryStore, HistoryStoreError, SOURCE_MANUAL, STATUS_OK,
)


@pytest.fixture
def store():
    history = HistoryStore()
    try:
        yield history
    finally:
        history.close()


def test_multiple_journals_attach_to_one_history_run_idempotently(store, tmp_path):
    run = store.start_run(SOURCE_MANUAL, "manual", "script.json")
    first, second = str(tmp_path / "first.jsonl"), str(tmp_path / "second.jsonl")
    assert store.attach_journal(run, first, "one")
    assert store.attach_journal(run, first, "one")
    assert store.attach_journal(run, second, "two")
    links = store.journals_for_run(run)
    assert [(item.run_id, item.journal_path, item.journal_run_id) for item in links] == [
        (run, first, "one"), (run, second, "two"),
    ]
    assert not Path(first).exists() and not Path(second).exists()
    assert store.journals_for_run(run + 1) == []
    assert not store.attach_journal(run + 1, first, "unknown")


@pytest.mark.parametrize("field", ["journal_path", "journal_run_id"])
def test_empty_journal_metadata_is_refused(store, field):
    run = store.start_run(SOURCE_MANUAL, "manual", "script.json")
    arguments = {"journal_path": "file.jsonl", "journal_run_id": "run"}
    arguments[field] = ""
    with pytest.raises(HistoryStoreError):
        store.attach_journal(run, **arguments)
    assert store.journals_for_run(run) == []


@pytest.mark.parametrize("operation", ["clear", "prune"])
def test_history_cleanup_removes_links_but_never_deletes_journal_files(store, tmp_path, operation):
    paths = [tmp_path / "first.jsonl", tmp_path / "second.jsonl"]
    runs = []
    for index, path in enumerate(paths):
        path.write_text("user-owned journal bytes", encoding="utf-8")
        run = store.start_run(SOURCE_MANUAL, str(index), "script.json", started_at=index)
        store.attach_journal(run, str(path), str(index))
        store.finish_run(run, STATUS_OK)
        runs.append(run)
    if operation == "clear":
        assert store.clear() == 2
        assert store.journals_for_run(runs[1]) == []
    else:
        assert store.prune(1) == 1
        assert len(store.journals_for_run(runs[1])) == 1
    assert store.journals_for_run(runs[0]) == []
    assert all(path.read_text(encoding="utf-8") == "user-owned journal bytes" for path in paths)


def test_old_history_schema_migrates_without_changing_existing_rows(tmp_path):
    sqlite3 = pytest.importorskip("sqlite3")
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE runs(id INTEGER PRIMARY KEY AUTOINCREMENT, source_type TEXT,
                source_id TEXT, script_path TEXT, started_at REAL, finished_at REAL,
                status TEXT, error_text TEXT);
            INSERT INTO runs VALUES(1,'manual','legacy','old.json',1,2,'ok',NULL);
        """)
    history = HistoryStore(path)
    try:
        assert history.get_run(1).source_id == "legacy"
        assert history.attach_journal(1, "old.jsonl", "legacy-run")
        assert history.journals_for_run(1)[0].journal_run_id == "legacy-run"
    finally:
        history.close()
    reopened = HistoryStore(path)
    try:
        assert reopened.get_run(1).source_id == "legacy"
        assert reopened.journals_for_run(1)[0].journal_path == "old.jsonl"
    finally:
        reopened.close()


def test_failed_history_initialization_releases_the_connection(store, monkeypatch):
    from types import SimpleNamespace
    from je_auto_control.utils.run_history import history_store
    sqlite3 = pytest.importorskip("sqlite3")
    class FailingConnection(sqlite3.Connection):
        closed = False
        def executescript(self, _script):
            raise sqlite3.OperationalError("controlled schema failure")
        def close(self):
            self.closed = True
            super().close()
    connection = sqlite3.connect(":memory:", factory=FailingConnection)
    driver = SimpleNamespace(Row=sqlite3.Row, connect=lambda *_args, **_kwargs: connection)
    monkeypatch.setattr(history_store, "require_sqlite3", lambda: driver)
    try:
        with pytest.raises(HistoryStoreError, match="controlled schema failure"):
            store.attach_journal(1, "unused.jsonl", "unused")
        assert connection.closed and store._conn is None
    finally:
        connection.close()


def test_journal_scope_attaches_before_device_effects_and_restores_the_owner(store, tmp_path, monkeypatch):
    from je_auto_control.utils.run_history.context import HistoryBinding, bound_history, current_history
    run = store.start_run(SOURCE_MANUAL, "manual", "script.json")
    owner = HistoryBinding(store, run)
    path = tmp_path / "run.jsonl"
    reached = []
    def probe():
        links = store.journals_for_run(run)
        reached.append((links[0].journal_path, links[0].journal_run_id, current_history()))
    monkeypatch.setitem(executor.event_dict, "AC_history_probe", probe)
    with bound_history(owner):
        with journal_scope(ActionJournal(path), run_id="journal"):
            executor.execute_action([["AC_history_probe"]])
        assert current_history() is owner
    assert current_history() is None
    assert reached == [(str(path.resolve()), "journal", owner)]


def test_unknown_history_owner_prevents_the_action_before_any_effect(store, tmp_path, monkeypatch):
    from je_auto_control.utils.action_journal import ActionJournalError
    from je_auto_control.utils.run_history.context import HistoryBinding, bound_history
    reached = []
    monkeypatch.setitem(executor.event_dict, "AC_history_probe", lambda: reached.append(True))
    with bound_history(HistoryBinding(store, 999)), pytest.raises(ActionJournalError, match="history"):
        with journal_scope(ActionJournal(tmp_path / "no-effect.jsonl")):
            executor.execute_action([["AC_history_probe"]])
    assert reached == []


def test_history_bindings_restore_on_nested_failure_and_explicitly_clear_ambient_owners(store):
    from je_auto_control.utils.run_history.context import HistoryBinding, bound_history, current_history
    first = HistoryBinding(store, 1)
    second = HistoryBinding(store, 2)
    with bound_history(first):
        with pytest.raises(RuntimeError):
            with bound_history(second):
                assert current_history() is second
                raise RuntimeError("controlled")
        assert current_history() is first
        with bound_history(None):
            assert current_history() is None
        assert current_history() is first
    assert current_history() is None


@pytest.mark.parametrize("kind", ["parallel", "dag"])
def test_workers_keep_the_parent_history_when_they_start_their_own_journal(store, tmp_path, monkeypatch, kind):
    from je_auto_control.utils.run_history.context import HistoryBinding, bound_history
    run = store.start_run(SOURCE_MANUAL, "manual", "script.json")
    def capture(index):
        with journal_scope(ActionJournal(tmp_path / f"{index}.jsonl"), run_id=f"child-{index}"):
            executor.execute_action([["AC_history_inner"]])
    monkeypatch.setitem(executor.event_dict, "AC_history_link_capture_probe", capture)
    monkeypatch.setitem(executor.event_dict, "AC_history_inner", lambda: None)
    bodies = [[["AC_history_link_capture_probe", {"index": index}]] for index in range(2)]
    script = ([["AC_parallel", {"branches": bodies}]] if kind == "parallel" else
              [["AC_run_dag", {"definition": {"nodes": [
                  {"id": str(index), "actions": body} for index, body in enumerate(bodies)]}}]])
    with bound_history(HistoryBinding(store, run)):
        executor.execute_action(script, raise_on_error=True)
    assert {item.journal_run_id for item in store.journals_for_run(run)} == {"child-0", "child-1"}


@pytest.mark.parametrize("kind", ["scheduler", "trigger", "hotkey", "webhook", "email"])
def test_background_run_owners_link_explicit_journals_to_their_existing_row(kind, store, tmp_path, monkeypatch):
    from je_auto_control.utils.hotkey import hotkey_daemon
    from je_auto_control.utils.scheduler import scheduler
    from je_auto_control.utils.triggers import email_trigger, trigger_engine, webhook_server
    for module in (hotkey_daemon, scheduler, email_trigger, trigger_engine, webhook_server):
        monkeypatch.setattr(module, "default_history_store", store)
        monkeypatch.setattr(module, "capture_error_snapshot", lambda *_args: None)
    path = tmp_path / "events.jsonl"
    def capture():
        with journal_scope(ActionJournal(path), run_id="background"):
            executor.execute_action([["AC_history_inner"]])
    monkeypatch.setitem(executor.event_dict, "AC_history_link_capture_probe", capture)
    monkeypatch.setitem(executor.event_dict, "AC_history_inner", lambda: None)
    script = tmp_path / "actions.json"
    script.write_text(json.dumps([["AC_history_link_capture_probe"]]), encoding="utf-8")
    if kind == "scheduler":
        owner = scheduler.Scheduler()
        job = owner.add_job(str(script), 60)
        owner._fire(job, 0, 1_800_000_000)
    elif kind == "trigger":
        owner = trigger_engine.TriggerEngine()
        trigger = trigger_engine.FilePathTrigger("probe", str(script))
        owner.add(trigger)
        owner._fire(trigger, 0)
    elif kind == "hotkey":
        owner = hotkey_daemon.HotkeyDaemon()
        owner.bind("ctrl+alt+a", str(script), binding_id="probe")
        owner._fire_binding("probe")
    elif kind == "webhook":
        owner = webhook_server.WebhookTriggerServer()
        trigger = owner.add(path="/probe", script_path=str(script))
        owner.fire(trigger, {})
    else:
        owner = email_trigger.EmailTriggerWatcher()
        trigger = owner.add("imap.invalid", "user", "unused", str(script))
        owner._execute_with_history(trigger, {})
    rows = store.list_runs()
    assert len(rows) == 1 and rows[0].status == STATUS_OK
    links = store.journals_for_run(rows[0].id)
    assert [(item.journal_path, item.journal_run_id) for item in links] == [(str(path.resolve()), "background")]
