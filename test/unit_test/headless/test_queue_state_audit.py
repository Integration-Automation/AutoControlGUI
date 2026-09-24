"""Queue / durable-state defects from the 2026-09-24 audit.

A stale performer could still settle an item someone else had reclaimed, and
reclaims never counted as retries; a failed resumable step was checkpointed
as done; an idempotency key whose work failed stayed in progress for good;
the dedup window and the outbox were shared across threads without a lock;
the S3 store listed a sibling prefix and stopped at one page; a negative
RateLimit-Reset became a negative sleep; and a watchdog rule that failed to
import its backend ended the watchdog thread.
"""
import sqlite3
import threading

import pytest

from je_auto_control.utils.artifact_store.s3_store import S3ArtifactStore
from je_auto_control.utils.bulkhead.bulkhead import next_delay
from je_auto_control.utils.checkpoint.checkpoint import CheckpointStore, run_resumable
from je_auto_control.utils.dedup_window.dedup_window import DedupWindow
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.idempotency.idempotency import IdempotencyStore
from je_auto_control.utils.outbox.outbox import Outbox
from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule
from je_auto_control.utils.work_queue.work_queue import WorkQueue


def _age_items(db, seconds):
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE work_items SET updated=updated-?", (seconds,))


def test_a_stale_performer_cannot_settle_a_reclaimed_item(tmp_path):
    db = str(tmp_path / "q.db")
    queue = WorkQueue(db)
    queue.add({"n": 1})
    first = queue.get_next()
    _age_items(db, 100)
    second = queue.get_next(stale_after_s=10)
    assert (first.id, first.claim, second.claim) == (second.id, 1, 2)
    assert second.retries == 1
    with pytest.raises(AutoControlException, match="claimed again"):
        queue.fail(first.id, "late", claim=first.claim)
    with pytest.raises(AutoControlException, match="claimed again"):
        queue.complete(first.id, claim=first.claim)
    queue.complete(second.id, claim=second.claim)
    assert queue.stats()["success"] == 1


def test_an_item_abandoned_max_retries_times_is_failed_not_reclaimed(tmp_path):
    db = str(tmp_path / "q.db")
    queue = WorkQueue(db)
    queue.add({"poison": True})
    for _ in range(3):
        assert queue.get_next(stale_after_s=10, max_retries=2) is not None
        _age_items(db, 100)
    assert queue.get_next(stale_after_s=10, max_retries=2) is None
    [item] = queue.list_items(status="failed")
    assert item.error.startswith("abandoned")


def test_an_existing_queue_database_gains_the_claim_column(tmp_path):
    db = str(tmp_path / "old.db")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE work_items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "queue TEXT NOT NULL, reference TEXT, data TEXT NOT NULL, "
            "status TEXT NOT NULL, retries INTEGER NOT NULL DEFAULT 0, "
            "error TEXT DEFAULT '', output TEXT DEFAULT '', updated REAL NOT NULL)")
        conn.execute("INSERT INTO work_items (queue, reference, data, status, updated) "
                     "VALUES ('default', '', '{}', 'new', 0)")
    item = WorkQueue(db).get_next()
    assert item.claim == 1


class _FailingSecondStep:
    """Executor stand-in: step 1 fails, and only raises when asked to."""

    def __init__(self):
        from je_auto_control.utils.executor.action_executor import Executor
        self.variables = Executor().variables
        self.ran = []

    def execute_action(self, actions, raise_on_error=False):
        self.ran.append(actions[0])
        if actions[0] == "bad" and raise_on_error:
            raise AutoControlException("step failed")
        return {actions[0]: "ok"}


def test_a_failed_resumable_step_is_retried_on_the_next_run(tmp_path):
    store = CheckpointStore(str(tmp_path / "cp.db"))
    runner = _FailingSecondStep()
    with pytest.raises(AutoControlException):
        run_resumable(["good", "bad", "later"], run_id="r", store=store, executor=runner)
    assert store.load("r").step_index == 1
    assert "later" not in runner.ran


def test_a_failed_idempotent_key_can_be_released_and_retried(tmp_path):
    store = IdempotencyStore()
    assert store.begin("k")["status"] == "new"
    assert store.begin("k")["status"] == "in_progress"
    assert store.release("k") is True
    assert store.begin("k")["status"] == "new"
    store.complete("k", {"ok": 1})
    assert store.release("k") is False
    path = store.save(str(tmp_path / "idem.json"))
    assert IdempotencyStore.load(path).get("k")["response"] == {"ok": 1}


def test_the_dedup_window_admits_one_first_sighting_across_threads():
    window = DedupWindow(60)
    for index in range(2000):
        window.mark(f"old-{index}")
    firsts = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        firsts.append(window.check_and_mark("same-id"))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert firsts.count(True) == 1


def test_concurrent_outbox_drains_send_each_entry_once():
    outbox = Outbox()
    for index in range(50):
        outbox.enqueue(index)
    delivered = []
    lock = threading.Lock()

    def sink(event):
        with lock:
            delivered.append(event)

    threads = [threading.Thread(target=outbox.drain, args=(sink,)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(delivered) == list(range(50))


class _PagedS3:
    def __init__(self, keys):
        self._keys = keys
        self.requests = []

    def list_objects_v2(self, **request):
        self.requests.append(dict(request))
        matching = [key for key in self._keys if key.startswith(request["Prefix"])]
        start = int(request.get("ContinuationToken", 0))
        page = matching[start:start + 2]
        more = start + 2 < len(matching)
        response = {"Contents": [{"Key": key} for key in page], "IsTruncated": more}
        if more:
            response["NextContinuationToken"] = str(start + 2)
        return response


def test_s3_list_stays_in_its_prefix_and_reads_every_page():
    client = _PagedS3(["run/a", "run/b", "run/c", "run2/secret"])
    store = S3ArtifactStore("bucket", client=client, prefix="run")
    assert store.list() == ["a", "b", "c"]
    assert client.requests[0]["Prefix"] == "run/"


def test_a_negative_ratelimit_reset_is_no_wait():
    response = {"headers": {"RateLimit-Remaining": "0", "RateLimit-Reset": "-5"}}
    assert next_delay(response) == 0.0


def test_a_rule_that_cannot_import_its_backend_does_not_end_the_watchdog():
    def matcher():
        raise ImportError("no window backend")

    watchdog = PopupWatchdog()
    watchdog.add_rule(WatchdogRule(name="r", matcher=matcher, action=lambda: None))
    assert watchdog.check_once() == 0
