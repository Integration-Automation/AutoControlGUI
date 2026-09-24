"""Regression tests for the orchestration-runner defects of the 2026-09-23 audit.

``run_saga`` ran each step leniently, so a failing step was never noticed and
nothing was rolled back. One device raising an exception outside a short list
aborted the whole device matrix, and a DAG runner raising a plain
``Exception`` escaped ``run_dag``. The work queue settled items that were not
in progress (requeueing finished work), and an observer rule removed during a
poll still fired. Commands here are probes on the executor -- no real input.
"""
import pytest

from je_auto_control.utils.dag.runner import run_dag
from je_auto_control.utils.device_matrix.matrix import run_on_devices
from je_auto_control.utils.exception.exceptions import AutoControlException, ImageNotFoundException
from je_auto_control.utils.executor import action_executor
from je_auto_control.utils.observer.observer import ScreenObserver
from je_auto_control.utils.saga.saga import run_saga
from je_auto_control.utils.work_queue.work_queue import WorkQueue


@pytest.fixture
def probe(monkeypatch):
    calls = []
    monkeypatch.setattr(action_executor.executor, "event_dict",
                        dict(action_executor.executor.event_dict))

    def _probe(tag="", fail=False):
        calls.append(tag)
        if fail:
            raise RuntimeError(f"{tag} failed")
        return tag

    action_executor.executor.event_dict["AC_probe"] = _probe
    return calls


def _step(name, fail=False, undo=True):
    spec = {"name": name, "action": [["AC_probe", {"tag": name, "fail": fail}]]}
    if undo:
        spec["compensation"] = [["AC_probe", {"tag": f"undo-{name}"}]]
    return spec


def test_a_failing_saga_step_rolls_back(probe):
    result = run_saga([_step("s1"), _step("s2", fail=True), _step("s3")])
    assert (result.ok, result.failed_step, result.compensated) == (False, "s2", ["s1"])
    assert probe == ["s1", "s2", "undo-s1"]


def test_one_device_failing_does_not_abort_the_matrix(monkeypatch):
    def fail_on_b(self, actions, raise_on_error=False, **_kwargs):
        if self.variables.get("device")["serial"] == "b":
            raise ImageNotFoundException("not on screen")
        return {}

    monkeypatch.setattr(action_executor.Executor, "execute_action", fail_on_b)
    devices = [{"platform": "android", "serial": serial} for serial in "abc"]
    report = run_on_devices([["AC_noop"]], devices)
    assert sorted(result.success for result in report.results) == [False, True, True]


def test_a_plain_exception_in_a_dag_node_fails_the_node():
    class MyError(Exception):
        pass

    def runner(node, _definition):
        if node.id == "a":
            raise MyError("boom")
        return "ok"

    raw = {"nodes": [{"id": "a", "actions": []},
                     {"id": "b", "actions": [], "depends_on": ["a"]}]}
    result = run_dag(raw, max_parallel=1, local_runner=runner)
    statuses = {node_id: node.status for node_id, node in result.nodes.items()}
    assert statuses == {"a": "failed", "b": "skipped"}


@pytest.fixture
def queue(tmp_path):
    return WorkQueue(str(tmp_path / "q.db"))


def test_a_finished_item_cannot_be_failed_back_into_the_queue(queue):
    item_id = queue.add({"n": 1})
    queue.get_next()
    queue.complete(item_id)
    with pytest.raises(AutoControlException, match="not in_progress"):
        queue.fail(item_id, "late failure")
    assert queue.get_next() is None


def test_an_unclaimed_item_cannot_be_completed(queue):
    item_id = queue.add({"n": 1})
    with pytest.raises(AutoControlException):
        queue.complete(item_id)
    with pytest.raises(AutoControlException):
        queue.complete(9999)


def test_a_stale_performer_cannot_undo_the_new_performers_outcome(queue):
    item_id = queue.add({"n": 1})
    queue.get_next()
    queue.get_next(stale_after_s=-1)          # re-claimed as stale
    queue.complete(item_id)                   # the second performer finishes
    with pytest.raises(AutoControlException):
        queue.fail(item_id, "first performer gives up")


def test_a_rule_removed_during_a_poll_does_not_fire():
    observer = ScreenObserver()
    fired = []

    def predicate():
        observer.remove("watch")              # removed while this poll runs
        return True

    observer.add("watch", predicate, lambda event, value: fired.append(event))
    observer.poll_once()
    assert fired == []
