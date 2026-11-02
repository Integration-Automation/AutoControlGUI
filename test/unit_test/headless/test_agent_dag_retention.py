"""Batch retention protects unresolved input and whole-graph evidence before any task cleanup."""
import json
import threading
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.dag import run_dag
from je_auto_control.utils.dag.batch_contract import bind_definition
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.work_queue.work_queue import WorkQueue
from .test_agent_dag_batches import graph, runtime as runtime
from .test_agent_dag_batch_loopback import service as service


EXPIRED = time.time() - 31 * 86400


def register(instance):
    return instance.batches.control("register", {"definition": graph()})


def age(instance, batch_id):
    with instance.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_dag_batches SET updated=? WHERE id=?", (EXPIRED, batch_id))
        connection.execute("UPDATE agent_tasks SET updated=?", (EXPIRED,))
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='work_items'").fetchone():
            connection.execute("UPDATE work_items SET updated=?", (EXPIRED,))


def test_expired_terminal_task_referenced_by_unstarted_batch_is_preserved(runtime):
    batch = register(runtime)
    node = bind_definition(batch["definition"], batch["batch_id"], batch["graph_hash"])["nodes"][0]
    task = runtime.submit(node["task"]["spec"], idempotency_key=node["task"]["idempotency_key"])
    runtime.cancel(task.task_id)
    age(runtime, batch["batch_id"])
    result = runtime.prune()
    assert result["deleted"] == []
    assert runtime.get(task.task_id).state == "cancelled"
    assert runtime.batches.control("get", {"batch_id": batch["batch_id"]})["state"] == "registered"


def test_expired_unused_registration_is_collected_without_starting_input(runtime):
    batch = register(runtime)
    age(runtime, batch["batch_id"])
    result = runtime.prune()
    assert result["deleted_batches"] == [batch["batch_id"]]
    with pytest.raises(AgentTaskError, match="batch does not exist"):
        runtime.batches.control("get", {"batch_id": batch["batch_id"]})


@pytest.mark.parametrize("state", ["running", "waiting_review", "approved"])
def test_unresolved_batches_and_delivery_records_outlive_thirty_days(runtime, state):
    batch = register(runtime)
    queue = WorkQueue(runtime.store.path, "agent_dag")
    item = queue.add({"fixture": True}, reference=batch["batch_id"])
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_dag_batches SET state=? WHERE id=?", (state, batch["batch_id"]))
        connection.execute("UPDATE work_items SET status='failed' WHERE id=?", (item,))
    age(runtime, batch["batch_id"])
    assert runtime.prune()["deleted_batches"] == []
    with runtime.store.connection() as connection:
        assert connection.execute("SELECT 1 FROM work_items WHERE id=?", (item,)).fetchone()


def test_batch_collection_is_owner_scoped_and_preserves_fresh_records(runtime):
    with authorization_scope(AuthorizationContext("alice", "operator")):
        first = register(runtime)
    with authorization_scope(AuthorizationContext("bob", "operator")):
        second = register(runtime)
    age(runtime, first["batch_id"])
    age(runtime, second["batch_id"])
    with authorization_scope(AuthorizationContext("bob", "operator")):
        fresh = register(runtime)
        assert runtime.prune()["deleted_batches"] == [second["batch_id"]]
        assert runtime.batches.control("get", {"batch_id": fresh["batch_id"]})["state"] == "registered"
    assert runtime.batches.control("get", {"batch_id": first["batch_id"]})["state"] == "registered"


def test_completed_batch_expires_with_owned_evidence_and_completed_delivery(service):
    client, host, target = service
    batch = register(host.runtime)
    assert run_dag(graph(), batch_id=batch["batch_id"]).succeeded
    queue = WorkQueue(host.runtime.store.path, "agent_dag")
    item = queue.add({"fixture": True}, reference=batch["batch_id"])
    with host.runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE work_items SET status='success' WHERE id=?", (item,))
    task_ids = [item.task_id for item in host.runtime.list()]
    age(host.runtime, batch["batch_id"])
    result = client.call("prune", {"keep_days": 30})
    assert result["deleted_batches"] == [batch["batch_id"]]
    assert set(result["deleted"]) == set(task_ids) and result["deleted_dag_deliveries"] == 1
    assert target.count == 2
    with host.runtime.store.connection() as connection:
        for table in ("agent_dag_batches", "agent_dag_nodes", "agent_dag_inputs", "agent_dag_local_tasks"):
            assert connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
    assert host.runtime.evidence.history.list_runs() == []


@pytest.mark.parametrize("status", ["new", "in_progress"])
def test_unretired_coordinator_delivery_blocks_batch_collection(runtime, status):
    batch = register(runtime)
    queue = WorkQueue(runtime.store.path, "agent_dag")
    item = queue.add({"fixture": True}, reference=batch["batch_id"])
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE work_items SET status=? WHERE id=?", (status, item))
    age(runtime, batch["batch_id"])
    assert runtime.prune()["deleted_batches"] == []


def test_orphan_cleanup_is_terminal_expired_host_scoped_and_queue_specific(runtime):
    queue = WorkQueue(runtime.store.path, "agent_dag")
    expired = queue.add({}, reference="deleted-batch")
    fresh = queue.add({}, reference="fresh-orphan")
    pending = queue.add({}, reference="pending-orphan")
    other = WorkQueue(runtime.store.path, "unrelated").add({}, reference="foreign")
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE work_items SET status='failed' WHERE id IN (?,?)", (expired, fresh))
        connection.execute("UPDATE work_items SET updated=? WHERE id=?", (EXPIRED, expired))
    with authorization_scope(AuthorizationContext("operator", "operator")):
        assert runtime.prune()["deleted_dag_deliveries"] == 0
    assert runtime.prune()["deleted_dag_deliveries"] == 1
    with runtime.store.connection() as connection:
        assert {row[0] for row in connection.execute("SELECT id FROM work_items")} == {fresh, pending, other}


@pytest.mark.parametrize("fault", ["queued_child", "held", "executing", "uncertain", "fresh_delivery", "phase"])
def test_completed_batch_keeps_its_gate_when_related_work_is_unsettled(service, fault):
    _client, host, _target = service
    instance = host.runtime
    batch = register(instance)
    assert run_dag(graph(), batch_id=batch["batch_id"]).succeeded
    task_id = instance.list()[0].task_id
    age(instance, batch["batch_id"])
    lease = None
    if fault == "queued_child":
        instance.submit(instance.store.get(task_id)["spec"])
    elif fault == "held":
        lease = instance.broker.acquire("fixture", task_id)
    elif fault == "executing":
        instance._executing.add(task_id)
    elif fault == "fresh_delivery":
        queue = WorkQueue(instance.store.path, "agent_dag")
        item = queue.add({}, reference=batch["batch_id"])
        with instance.store.connection(write=True) as connection:
            connection.execute("UPDATE work_items SET status='success' WHERE id=?", (item,))
    else:
        with instance.store.connection(write=True) as connection:
            if fault == "uncertain":
                connection.execute("UPDATE agent_actions SET status='uncertain' WHERE task_id=?", (task_id,))
            else:
                connection.execute("UPDATE agent_dag_nodes SET phase='unknown' WHERE batch_id=?", (batch["batch_id"],))
    try:
        result = instance.prune()
        assert result["deleted_batches"] == [] and result["deleted"] == []
        with instance.store.connection() as connection:
            assert connection.execute("SELECT 1 FROM agent_dag_local_tasks WHERE task_id=?", (task_id,)).fetchone()
    finally:
        instance._executing.discard(task_id)
        if lease is not None:
            instance.broker.release(lease, lambda: None)


def test_recovery_descendant_without_batch_tag_is_preserved_through_source_lineage(runtime):
    batch = register(runtime)
    spec = bind_definition(batch["definition"], batch["batch_id"], batch["graph_hash"])["nodes"][0]["task"]["spec"]
    source = runtime.submit(spec)
    runtime.cancel(source.task_id)
    child_spec = json.loads(json.dumps(spec))
    child_spec["options"].pop("dag_batch")
    child = runtime.submit(child_spec)
    runtime.cancel(child.task_id)
    with runtime.store.connection(write=True) as connection:
        connection.execute("INSERT INTO agent_task_recoveries VALUES (?,?,?,?,?)",
                           (child.task_id, source.task_id, "fixture-snapshot", "reviewed fixture", time.time()))
    age(runtime, batch["batch_id"])
    assert runtime.prune()["deleted"] == []
    assert runtime.get(source.task_id).state == runtime.get(child.task_id).state == "cancelled"


def test_begin_that_wins_the_batch_lock_prevents_collection_of_an_old_registration(runtime, monkeypatch):
    batch = register(runtime)
    age(runtime, batch["batch_id"])
    original = runtime._lock
    selected = threading.Event()
    results = []

    def notice_lock(identifier):
        if identifier == "dag:" + batch["batch_id"]:
            selected.set()
        return original(identifier)

    with original("dag:" + batch["batch_id"]):
        monkeypatch.setattr(runtime, "_lock", notice_lock)
        worker = threading.Thread(target=lambda: results.append(runtime.prune()))
        worker.start()
        assert selected.wait(5)
        runtime.batches.control("begin", {"batch_id": batch["batch_id"], "definition": graph(), "max_parallel": 4})
    worker.join(5)
    assert not worker.is_alive() and results[0]["deleted_batches"] == []
    assert runtime.batches.control("get", {"batch_id": batch["batch_id"]})["state"] == "running"
