"""Headless tests for the transactional work queue (dispatcher/performer).

Uses a temporary SQLite file; no external services. Covers FIFO claim,
dedup, completion, application-vs-business failure semantics, stats, and
the executor/MCP/builder wiring."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.work_queue import WorkQueue


@pytest.fixture()
def q(tmp_path):
    return WorkQueue(str(tmp_path / "q.db"), "test")


def test_add_and_get_next_is_fifo(q):
    first, second = q.add({"n": 1}), q.add({"n": 2})
    assert first < second
    item = q.get_next()
    assert item.data == {"n": 1}
    assert item.status == "in_progress"
    assert q.get_next().data == {"n": 2}
    assert q.get_next() is None


def test_dedupe_by_reference(q):
    assert q.add({"x": 1}, reference="r1") is not None
    assert q.add({"x": 2}, reference="r1") is None      # live duplicate
    item = q.get_next()
    q.complete(item.id)
    assert q.add({"x": 3}, reference="r1") is not None  # ref free again


def test_complete_records_success(q):
    q.add({"n": 1})
    item = q.get_next()
    q.complete(item.id, output={"ok": True})
    stats = q.stats()
    assert stats["success"] == 1 and stats["new"] == 0


def test_application_error_retries_then_fails(q):
    q.add({"n": 1})
    item = q.get_next()
    assert q.fail(item.id, "boom", kind="application", max_retries=2) == "new"
    item = q.get_next()
    assert item.retries == 1
    assert q.fail(item.id, "boom", max_retries=2) == "new"
    item = q.get_next()
    assert item.retries == 2
    assert q.fail(item.id, "boom", max_retries=2) == "failed"
    assert q.stats()["failed"] == 1


def test_business_error_never_retries(q):
    q.add({"n": 1})
    item = q.get_next()
    assert q.fail(item.id, "bad data", kind="business") == "failed"
    assert q.stats()["failed"] == 1
    assert q.get_next() is None


def test_list_items_by_status(q):
    q.add({"n": 1})
    q.add({"n": 2})
    assert len(q.list_items(status="new")) == 2
    assert len(q.list_items(status="success")) == 0


def test_executor_and_mcp_wiring(tmp_path):
    db = str(tmp_path / "e.db")
    rec = ac.execute_action(
        [["AC_queue_add", {"db": db, "data": {"n": 1}, "name": "t"}]])
    assert any("id" in str(v) for v in rec.values())
    nxt = ac.execute_action([["AC_queue_next", {"db": db, "name": "t"}]])
    assert any("'n': 1" in str(v) for v in nxt.values())
    known = ac.executor.known_commands()
    assert {"AC_queue_add", "AC_queue_next", "AC_queue_complete",
            "AC_queue_fail", "AC_queue_stats"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_queue_add", "ac_queue_next", "ac_queue_complete",
            "ac_queue_fail", "ac_queue_stats"} <= names


def test_facade_and_builder():
    assert ac.WorkQueue is WorkQueue
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    qcmds = {"AC_queue_add", "AC_queue_next", "AC_queue_complete",
             "AC_queue_fail", "AC_queue_stats"}
    assert qcmds <= cmds
    assert qcmds <= ac.executor.known_commands()
