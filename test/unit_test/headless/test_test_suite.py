"""Headless tests for the QA suite runner, reports, and quarantine."""
import defusedxml.ElementTree as ET
from pathlib import Path

import pytest

from je_auto_control.utils.quarantine.store import QuarantineStore
from je_auto_control.utils.test_suite import (
    STATUS_PASSED, run_suite, to_junit_xml,
    write_allure_results, write_junit_xml,
)

_PASS = ["AC_assert_window", {"title": "zzz_no_window", "exists": False}]
_FAIL = ["AC_assert_window", {"title": "zzz_no_window", "exists": True}]


def _spec():
    return {
        "name": "Demo",
        "setup": [["AC_set_var", {"name": "base", "value": 1}]],
        "cases": [
            {"name": "passes", "tags": ["smoke"], "actions": [_PASS]},
            {"name": "fails", "actions": [_FAIL]},
            {"name": "each", "as": "row",
             "data": {"kind": "inline", "rows": [{"u": "a"}, {"u": "b"}]},
             "actions": [["AC_set_var", {"name": "u", "value": "${row.u}"}]]},
        ],
    }


def test_run_suite_scores_cases():
    result = run_suite(_spec(), respect_quarantine=False)
    assert result.total == 4
    assert result.passed == 3
    assert result.failed == 1
    assert result.errored == 0
    assert result.success is False
    names = [c.name for c in result.cases]
    assert names == ["passes", "fails", "each[0]", "each[1]"]


def test_run_suite_tag_filter():
    result = run_suite(_spec(), tags=["smoke"], respect_quarantine=False)
    assert result.total == 1
    assert result.cases[0].name == "passes"
    assert result.cases[0].status == STATUS_PASSED


def test_setup_failure_skips_cases():
    spec = {
        "name": "S", "setup": [_FAIL],
        "cases": [{"name": "c", "actions": [_PASS]}],
    }
    result = run_suite(spec, respect_quarantine=False)
    assert result.setup_error is not None
    assert result.total == 0
    assert result.success is False


def test_quarantine_skips_named_case(monkeypatch):
    import je_auto_control.utils.quarantine as q
    monkeypatch.setattr(q, "quarantined_names", lambda: {"fails"})
    result = run_suite(_spec(), respect_quarantine=True)
    fails = next(c for c in result.cases if c.name == "fails")
    assert fails.status == "skipped"
    assert fails.message == "quarantined"
    # the failing case is now skipped, so the suite has no failures
    assert result.failed == 0


def test_junit_xml_is_wellformed():
    result = run_suite(_spec(), respect_quarantine=False)
    xml = to_junit_xml(result)
    root = ET.fromstring(xml)
    suite = root.find("testsuite")
    assert suite.attrib["tests"] == "4"
    assert suite.attrib["failures"] == "1"
    failures = root.findall(".//failure")
    assert len(failures) == 1


def test_write_junit_and_allure(tmp_path: Path):
    result = run_suite(_spec(), respect_quarantine=False)
    junit = write_junit_xml(result, str(tmp_path / "junit.xml"))
    assert Path(junit).is_file()
    allure = write_allure_results(result, str(tmp_path / "allure"))
    assert len(allure) == 4
    assert all(Path(p).is_file() for p in allure)


# === quarantine store ======================================================

def test_quarantine_store_roundtrip(tmp_path: Path):
    store = QuarantineStore(path=tmp_path / "q.json")
    store.add("flaky.json", reason="manual", flip_rate=0.8)
    assert store.is_quarantined("flaky.json")
    assert "flaky.json" in store.names()
    # persisted across instances
    reloaded = QuarantineStore(path=tmp_path / "q.json")
    assert reloaded.is_quarantined("flaky.json")
    assert reloaded.remove("flaky.json") is True
    assert reloaded.remove("flaky.json") is False


def test_auto_quarantine_from_flakiness(tmp_path: Path):
    from je_auto_control.utils.quarantine.store import (
        auto_quarantine_from_flakiness,
    )
    from je_auto_control.utils.run_history.history_store import HistoryStore
    import je_auto_control.utils.flakiness as flak

    history = HistoryStore()
    for status in ["ok", "error", "ok", "error"]:
        run_id = history.start_run("manual", "j", "flaky.json")
        history.finish_run(run_id, status)

    real_analyze = flak.analyze_flakiness

    def _patched(limit=500, min_runs=2, group_by="script_path"):
        return real_analyze(
            store=history, limit=limit, min_runs=min_runs, group_by=group_by,
        )

    store = QuarantineStore(path=tmp_path / "q.json")
    monkey = pytest.MonkeyPatch()
    monkey.setattr(flak, "analyze_flakiness", _patched)
    try:
        added = auto_quarantine_from_flakiness(
            flip_rate_threshold=0.5, min_runs=2, store=store,
        )
    finally:
        monkey.undo()
    assert any(e.name == "flaky.json" for e in added)
    assert store.is_quarantined("flaky.json")
