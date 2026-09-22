"""Regression tests for the SQLite store defects of the 2026-09-23 audit.

A crashed performer left its work item in progress for good; two dispatchers
could enqueue the same reference; ``fail`` on an unknown id reported a
requeue. Three stores never closed a connection. ``sqlite3.Error`` from the
run history and the audit log escaped every boundary that contains the
framework's errors, and two audit-log writers on one file broke its chain.
"""
import gc
from contextlib import closing
import sqlite3
import threading
import time
import warnings

import pytest

from je_auto_control.utils.agent_memory.agent_memory import AgentMemory
from je_auto_control.utils.checkpoint.checkpoint import CheckpointStore
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.remote_desktop.audit_log import AuditLog, AuditLogError
from je_auto_control.utils.run_history.history_store import HistoryStore, HistoryStoreError
from je_auto_control.utils.work_queue import work_queue as wq


@pytest.fixture
def queue(tmp_path):
    return wq.WorkQueue(str(tmp_path / "q.db"))


def test_a_stale_claim_can_be_reclaimed(queue, tmp_path):
    item_id = queue.add({"n": 1}, reference="r1")
    assert queue.get_next().id == item_id          # a performer claims it, then dies
    with closing(sqlite3.connect(tmp_path / "q.db")) as conn, conn:
        conn.execute("UPDATE work_items SET updated=?", (time.time() - 3600,))
    assert queue.get_next() is None, "without a lease nothing changes"
    reclaimed = queue.get_next(stale_after_s=60)
    assert reclaimed is not None and reclaimed.id == item_id


def test_a_fresh_claim_is_not_reclaimed(queue):
    queue.add({"n": 1})
    queue.get_next()
    assert queue.get_next(stale_after_s=60) is None


def test_two_dispatchers_cannot_both_enqueue_a_reference(queue, monkeypatch):
    barrier = threading.Barrier(2, timeout=1)
    real_has_pending = wq.WorkQueue._has_pending

    def racing_has_pending(self, conn, reference):
        found = real_has_pending(self, conn, reference)
        try:
            barrier.wait()  # both would pass the check together, were it not in a transaction
        except threading.BrokenBarrierError:
            pass
        return found

    monkeypatch.setattr(wq.WorkQueue, "_has_pending", racing_has_pending)
    results = []
    threads = [threading.Thread(target=lambda: results.append(queue.add({}, reference="dup")))
               for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(None) == 1
    assert len(queue.list_items()) == 1


def test_failing_an_unknown_item_raises(queue):
    with pytest.raises(AutoControlException, match="no work item"):
        queue.fail(9999, "boom")


def test_the_stores_close_their_connections(tmp_path):
    gc.collect()  # connections leaked by earlier tests warn when collected
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        queue = wq.WorkQueue(str(tmp_path / "q.db"))
        queue.add({})
        queue.stats()
        CheckpointStore(str(tmp_path / "c.db")).load("run")
        AgentMemory(str(tmp_path / "m.db")).recent()
        gc.collect()
    assert not [w for w in caught if "unclosed database" in str(w.message)]


def _corrupt(path):
    path.write_bytes(b"this is not a database" * 100)
    return path


def test_a_corrupt_history_database_raises_a_framework_error(tmp_path):
    store = HistoryStore(_corrupt(tmp_path / "history.db"))
    with pytest.raises(HistoryStoreError):
        store.start_run("hotkey", "b1", "s.json")
    assert issubclass(HistoryStoreError, AutoControlException)


def test_a_corrupt_audit_database_raises_a_framework_error(tmp_path):
    with pytest.raises(AuditLogError):
        AuditLog(_corrupt(tmp_path / "audit.db"))


def test_two_audit_writers_on_one_file_keep_the_chain(tmp_path):
    first, second = AuditLog(tmp_path / "audit.db"), AuditLog(tmp_path / "audit.db")
    first.log("a")
    second.log("b")
    first.log("c")
    assert first.verify_chain().ok
