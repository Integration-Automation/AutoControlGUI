"""A run-history row names the action-journal run that holds its actions."""
import sqlite3

import pytest

from je_auto_control.utils.action_journal import recorder
from je_auto_control.utils.run_history.history_store import HistoryStore

_OLD_SCHEMA = """
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL, source_id TEXT NOT NULL, script_path TEXT NOT NULL,
    started_at REAL NOT NULL, finished_at REAL, status TEXT NOT NULL,
    error_text TEXT, artifact_path TEXT
);
INSERT INTO runs (source_type, source_id, script_path, started_at, status)
VALUES ('manual', 'old', 'old.json', 1.0, 'ok');
"""


@pytest.fixture(autouse=True)
def _journal_off():
    recorder.stop_action_journal()
    yield
    recorder.stop_action_journal()


def test_a_run_started_while_a_journal_is_on_is_linked_to_it(tmp_path):
    store = HistoryStore()
    before = store.start_run("manual", "a", "a.json")
    journal = tmp_path / "journal.jsonl"
    recorder.start_action_journal(journal, run_id="run-77")
    during = store.start_run("scheduler", "b", "b.json")
    recorder.stop_action_journal()
    assert store.get_run(before).journal_run_id is None
    assert store.get_run(before).journal_path is None
    linked = store.get_run(during)
    assert linked.journal_run_id == "run-77"
    assert linked.journal_path == str(journal.resolve())
    assert store.list_runs()[0].journal_run_id == "run-77"


def test_an_explicit_link_wins_and_can_be_set_later():
    store = HistoryStore()
    run = store.start_run("manual", "a", "a.json", journal_path="j.jsonl",
                          journal_run_id="mine")
    assert store.get_run(run).journal_run_id == "mine"
    assert store.link_journal(run, "other.jsonl", "later") is True
    assert (store.get_run(run).journal_path, store.get_run(run).journal_run_id) == (
        "other.jsonl", "later")
    assert store.link_journal(9999, "x", "y") is False


def test_an_existing_database_gains_the_columns_and_keeps_its_rows(tmp_path):
    path = tmp_path / "history.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(_OLD_SCHEMA)
    conn.close()
    store = HistoryStore(path)
    try:
        old = store.list_runs()[0]
        assert (old.source_id, old.journal_path, old.journal_run_id) == ("old", None, None)
        run = store.start_run("manual", "new", "new.json", journal_path="j.jsonl",
                              journal_run_id="r1")
        assert store.get_run(run).journal_run_id == "r1"
    finally:
        store.close()


def test_clearing_history_never_deletes_the_journal_file(tmp_path):
    journal = tmp_path / "journal.jsonl"
    journal.write_text("", encoding="utf-8")
    store = HistoryStore()
    store.start_run("manual", "a", "a.json", journal_path=str(journal),
                    journal_run_id="r1")
    assert store.clear() == 1
    assert journal.exists()


def test_executor_and_mcp_rows_carry_the_link(monkeypatch):
    from je_auto_control.utils.run_history import history_store
    from je_auto_control.utils.mcp_server.tools import _handlers_runs
    store = HistoryStore()
    store.start_run("manual", "a", "a.json", journal_path="j.jsonl", journal_run_id="r1")
    monkeypatch.setattr(history_store, "default_history_store", store)
    row = _handlers_runs.list_run_history()[0]
    assert (row["journal_path"], row["journal_run_id"]) == ("j.jsonl", "r1")
