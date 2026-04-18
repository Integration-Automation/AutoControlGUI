"""Tests for the run history store and its scheduler/trigger/hotkey hooks."""
import time

import pytest

from je_auto_control.utils.run_history import history_store as history_mod
from je_auto_control.utils.run_history.history_store import (
    SOURCE_HOTKEY, SOURCE_SCHEDULER, SOURCE_TRIGGER, STATUS_ERROR, STATUS_OK,
    STATUS_RUNNING, HistoryStore, RunRecord,
)


@pytest.fixture
def store():
    s = HistoryStore(path=":memory:")
    try:
        yield s
    finally:
        s.close()


def test_start_run_creates_row_with_running_status(store):
    run_id = store.start_run(SOURCE_SCHEDULER, "job42", "a.json")
    record = store.get_run(run_id)
    assert isinstance(record, RunRecord)
    assert record.source_type == SOURCE_SCHEDULER
    assert record.source_id == "job42"
    assert record.status == STATUS_RUNNING
    assert record.finished_at is None
    assert record.duration_seconds is None


def test_finish_run_marks_ok(store):
    run_id = store.start_run(SOURCE_TRIGGER, "t1", "s.json")
    assert store.finish_run(run_id, STATUS_OK) is True
    record = store.get_run(run_id)
    assert record.status == STATUS_OK
    assert record.finished_at is not None
    assert record.duration_seconds is not None
    assert record.duration_seconds >= 0.0


def test_finish_run_captures_error_text(store):
    run_id = store.start_run(SOURCE_HOTKEY, "hk1", "x.json")
    store.finish_run(run_id, STATUS_ERROR, error_text="boom")
    record = store.get_run(run_id)
    assert record.status == STATUS_ERROR
    assert record.error_text == "boom"


def test_finish_run_rejects_running_status(store):
    run_id = store.start_run(SOURCE_SCHEDULER, "j", "p")
    with pytest.raises(ValueError):
        store.finish_run(run_id, STATUS_RUNNING)


def test_finish_run_returns_false_for_unknown_id(store):
    assert store.finish_run(99999, STATUS_OK) is False


def test_start_run_validates_source(store):
    with pytest.raises(ValueError):
        store.start_run("bogus", "id", "path")


def test_list_runs_orders_newest_first(store):
    store.start_run(SOURCE_SCHEDULER, "a", "1.json", started_at=100.0)
    store.start_run(SOURCE_SCHEDULER, "b", "2.json", started_at=200.0)
    store.start_run(SOURCE_SCHEDULER, "c", "3.json", started_at=150.0)
    records = store.list_runs(limit=10)
    assert [r.source_id for r in records] == ["b", "c", "a"]


def test_list_runs_filters_by_source(store):
    store.start_run(SOURCE_SCHEDULER, "s1", "x")
    store.start_run(SOURCE_TRIGGER, "t1", "y")
    store.start_run(SOURCE_HOTKEY, "h1", "z")
    only_triggers = store.list_runs(source_type=SOURCE_TRIGGER)
    assert len(only_triggers) == 1
    assert only_triggers[0].source_id == "t1"


def test_list_runs_respects_limit(store):
    for i in range(5):
        store.start_run(SOURCE_SCHEDULER, f"j{i}", "p")
    assert len(store.list_runs(limit=3)) == 3
    assert store.list_runs(limit=0) == []


def test_count_and_clear(store):
    store.start_run(SOURCE_SCHEDULER, "a", "p")
    store.start_run(SOURCE_TRIGGER, "b", "p")
    assert store.count() == 2
    assert store.count(source_type=SOURCE_TRIGGER) == 1
    assert store.clear() == 2
    assert store.count() == 0


def test_prune_keeps_latest(store):
    for i in range(6):
        store.start_run(SOURCE_SCHEDULER, f"j{i}", "p",
                        started_at=100.0 + i)
    removed = store.prune(keep_latest=2)
    assert removed == 4
    remaining = store.list_runs(limit=10)
    assert [r.source_id for r in remaining] == ["j5", "j4"]


def test_scheduler_records_history(monkeypatch, store):
    from je_auto_control.utils.scheduler import scheduler as sched_mod

    monkeypatch.setattr(sched_mod, "default_history_store", store)
    monkeypatch.setattr(sched_mod, "read_action_json", lambda _: [["AC_noop"]])

    sched = sched_mod.Scheduler(
        executor=lambda actions: None, tick_seconds=0.05,
    )
    sched.add_job("fake.json", interval_seconds=0.05, repeat=False)
    sched.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not store.list_runs():
            time.sleep(0.05)
    finally:
        sched.stop(timeout=1.0)
    runs = store.list_runs()
    assert runs, "scheduler should have recorded a run"
    assert runs[0].source_type == SOURCE_SCHEDULER
    assert runs[0].status == STATUS_OK


def test_scheduler_records_error(monkeypatch, store):
    from je_auto_control.utils.scheduler import scheduler as sched_mod

    def boom(_):
        raise RuntimeError("fail")

    monkeypatch.setattr(sched_mod, "default_history_store", store)
    monkeypatch.setattr(sched_mod, "read_action_json", boom)

    sched = sched_mod.Scheduler(
        executor=lambda actions: None, tick_seconds=0.05,
    )
    sched.add_job("fake.json", interval_seconds=0.05, repeat=False)
    sched.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not store.list_runs():
            time.sleep(0.05)
    finally:
        sched.stop(timeout=1.0)
    runs = store.list_runs()
    assert runs and runs[0].status == STATUS_ERROR
    assert "fail" in (runs[0].error_text or "")


def test_default_store_path_under_home():
    assert history_mod._default_history_path().parent.name == ".je_auto_control"


def test_executor_history_commands(monkeypatch, store):
    from je_auto_control.utils.executor import action_executor

    monkeypatch.setattr(action_executor, "default_history_store", store)
    store.start_run(SOURCE_SCHEDULER, "j", "p")
    rows = action_executor._history_list_as_dicts(limit=10)
    assert rows and rows[0]["source_type"] == SOURCE_SCHEDULER
