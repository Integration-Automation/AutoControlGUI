"""Headless tests for flaky-test detection over run history."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.flakiness import (
    FlakinessReport, analyze_flakiness,
)
from je_auto_control.utils.run_history.history_store import HistoryStore


@pytest.fixture
def store() -> HistoryStore:
    return HistoryStore()  # in-memory


def _record(store: HistoryStore, source_id: str, script: str, status: str):
    run_id = store.start_run("manual", source_id, script)
    store.finish_run(run_id, status)


def test_facade_export():
    assert hasattr(ac, "analyze_flakiness")


def test_flaky_script_detected(store):
    for status in ["ok", "error", "ok", "error"]:
        _record(store, "job1", "flaky.json", status)
    report = analyze_flakiness(store=store, min_runs=2)
    assert isinstance(report, FlakinessReport)
    entry = report.entries[0]
    assert entry.key == "flaky.json"
    assert entry.flaky is True
    assert entry.ok == 2 and entry.error == 2
    assert entry.flips == 3
    assert entry.flip_rate == 1.0
    assert report.flaky_count == 1


def test_stable_script_not_flaky(store):
    for _ in range(3):
        _record(store, "job2", "stable.json", "ok")
    report = analyze_flakiness(store=store, min_runs=2)
    entry = report.entries[0]
    assert entry.flaky is False
    assert entry.flips == 0
    assert entry.pass_rate == 1.0
    assert report.flaky_count == 0


def test_min_runs_filters_out_short_history(store):
    _record(store, "job3", "once.json", "error")
    report = analyze_flakiness(store=store, min_runs=2)
    assert report.entries == []


def test_group_by_source_id(store):
    _record(store, "nightly", "a.json", "ok")
    _record(store, "nightly", "b.json", "error")
    report = analyze_flakiness(store=store, min_runs=2, group_by="source_id")
    assert report.entries[0].key == "nightly"
    assert report.entries[0].total_runs == 2


def test_invalid_group_by_raises(store):
    with pytest.raises(ValueError):
        analyze_flakiness(store=store, group_by="bogus")


def test_running_runs_ignored(store):
    _record(store, "job4", "x.json", "ok")
    store.start_run("manual", "job4", "x.json")  # left running
    _record(store, "job4", "x.json", "error")
    report = analyze_flakiness(store=store, min_runs=2)
    entry = report.entries[0]
    assert entry.total_runs == 2  # the in-flight run is excluded
