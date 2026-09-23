"""Regression tests for the QA-subsystem defects of the 2026-09-23 audit.

A setup failure was missing from the JUnit counts and from Allure entirely; a
failed soft-assert batch scored *error* and a lenient run swallowed it;
``assert_http`` crashed on read timeouts and dropped connections;
``assert_eventually`` looped forever on a NaN timeout; one malformed case (or
quarantine entry) aborted the whole suite; string tags matched letter by
letter; equal timestamps listed runs oldest-first; ``critical_steps(top=0)``
returned a step. Every action is a probe on a private executor.
"""
import json
import socket
import threading
import xml.etree.ElementTree as ET  # nosec B405  # reason: parses XML this test just generated

import pytest

from je_auto_control.utils.assertion.assertions import assert_http
from je_auto_control.utils.assertion.combinators import assert_eventually
from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlAssertionException,
)
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.quarantine.store import QuarantineStore
from je_auto_control.utils.run_history.history_store import SOURCE_MANUAL, HistoryStore
from je_auto_control.utils.soft_assert import SoftAssertions
from je_auto_control.utils.step_timeline.step_timeline import critical_steps
from je_auto_control.utils.test_suite.reports import to_allure_results, to_junit_xml
from je_auto_control.utils.test_suite.runner import run_suite


@pytest.fixture
def executor():
    runner = Executor()

    def fail():
        raise AutoControlAssertionException("boom")

    runner.event_dict["AC_probe_ok"] = lambda: "ok"
    runner.event_dict["AC_probe_fail"] = fail
    return runner


def _suite(executor, cases, **kwargs):
    return run_suite({"name": "s", "cases": cases, **kwargs}, executor=executor,
                     respect_quarantine=False)


def test_junit_counts_a_setup_failure(executor):
    result = _suite(executor, [{"name": "c", "actions": [["AC_probe_ok"]]}],
                    setup=[["AC_probe_fail"]])
    suite = ET.fromstring(to_junit_xml(result)).find("testsuite")  # nosec B314  # reason: our own output
    assert (suite.get("tests"), suite.get("errors")) == ("1", "1")
    assert suite.get("timestamp")


def test_allure_reports_a_setup_failure(executor):
    result = _suite(executor, [], setup=[["AC_probe_fail"]])
    payloads = to_allure_results(result)
    assert [(p["name"], p["status"]) for p in payloads] == [("<setup>", "broken")]


def test_allure_survives_a_lone_surrogate(executor):
    result = _suite(executor, [{"name": "bad\ud800", "actions": [["AC_probe_ok"]]}])
    json.dumps(to_allure_results(result), ensure_ascii=False).encode("utf-8")


def test_a_failed_soft_assert_batch_is_an_assertion_failure():
    soft = SoftAssertions(raise_on_exit=False)
    soft.check(False, "x")
    with pytest.raises(AutoControlAssertionException) as caught:
        soft.assert_all()
    assert isinstance(caught.value, AutoControlActionException), "old except clauses still match"


def _silent_server(close_immediately):
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    held = []

    def accept():
        conn, _ = server.accept()
        conn.recv(4096)
        if close_immediately:
            conn.close()
        else:
            held.append(conn)

    threading.Thread(target=accept, daemon=True).start()
    return server, held


@pytest.mark.parametrize("close_immediately", [False, True])
def test_assert_http_scores_a_dead_server_as_failed(close_immediately):
    server, held = _silent_server(close_immediately)
    try:
        result = assert_http(f"http://127.0.0.1:{server.getsockname()[1]}/", timeout=0.5,
                             raise_on_fail=False)
        assert result.passed is False
    finally:
        for conn in held:
            conn.close()
        server.close()


@pytest.mark.parametrize("kwargs", [{"timeout": float("nan")}, {"interval": float("nan")}])
def test_assert_eventually_refuses_nan(tmp_path, kwargs):
    spec = {"kind": "file", "path": str(tmp_path / "never-created")}
    with pytest.raises(AutoControlAssertionException, match="number"):
        assert_eventually(spec, **kwargs)


def test_a_malformed_case_does_not_abort_the_suite(executor):
    result = _suite(executor, [{"name": "bad", "tags": 5, "actions": []},
                               {"name": "good", "actions": [["AC_probe_ok"]]}])
    assert [(case.name, case.status) for case in result.cases] == [("bad", "error"), ("good", "passed")]


def test_string_tags_are_one_tag(executor):
    result = run_suite({"name": "s", "cases": [{"name": "c", "tags": "smoke", "actions": []}]},
                       executor=executor, tags=["s"], respect_quarantine=False)
    assert result.cases == []
    result = run_suite({"name": "s", "cases": [{"name": "c", "tags": "smoke", "actions": []}]},
                       executor=executor, tags="smoke", respect_quarantine=False)
    assert [case.tags for case in result.cases] == [["smoke"]]


@pytest.mark.parametrize("entry", [{"name": "a", "added_at": None}, {"name": "a", "added_at": "x"},
                                   {"name": ["a"]}])
def test_a_bad_quarantine_entry_does_not_break_the_store(tmp_path, entry):
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"entries": [entry, {"name": "ok", "added_at": 1.0}]}), encoding="utf-8")
    assert "ok" in QuarantineStore(str(path)).names()


def test_runs_with_equal_timestamps_are_newest_first(tmp_path):
    store = HistoryStore(str(tmp_path / "h.db"))
    ids = [store.start_run(SOURCE_MANUAL, "x", "flow.json", started_at=100.0) for _ in range(3)]
    assert [run.id for run in store.list_runs()] == ids[::-1]


def test_critical_steps_top_zero_is_empty():
    assert critical_steps([{"name": "a", "duration": 1.0}], top=0) == []
