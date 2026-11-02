"""Whole-batch continuation requires explicit per-node decisions and never resends an uncertain claim."""
import threading
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.dag import run_dag
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.agent_runtime.origin_policy import origin_scope
from .test_agent_origin_policy import origin_directory as origin_directory
from .test_agent_dag_batch_loopback import service as service
from .test_agent_dag_batches import graph


@pytest.fixture
def stopped(service, monkeypatch):
    client, instance, target = service
    definition = graph()
    batch = client.call("dag", {"operation": "register", "request": {"definition": definition}})
    stop = threading.Event()
    original = AgentRuntimeClient.call

    def after_first_record(self, operation, body=None, **kwargs):
        result = original(self, operation, body, **kwargs)
        if (operation == "dag" and body.get("operation") == "record"
                and body["request"]["node_id"] == "a"):
            stop.set()
        return result

    monkeypatch.setattr(AgentRuntimeClient, "call", after_first_record)
    result = run_dag(definition, batch_id=batch["batch_id"], stop_event=stop)
    assert not result.succeeded and target.count == 1
    return client, instance, target, batch, definition


def review(client, batch, definition, **fields):
    return client.call("dag", {"operation": "review_continuation", "request": {
        "batch_id": batch["batch_id"], "definition": definition, **fields}})


def approval(value):
    return {key: value[key] for key in ("batch_id", "definition", "snapshot", "decisions")} | {
        "note": "Reviewed the whole graph, completed parent and never-dispatched child"}


def test_explicit_whole_graph_continuation_adopts_parent_and_dispatches_only_pending_child(stopped):
    client, _instance, target, batch, definition = stopped
    value = review(client, batch, definition)
    assert value["can_approve"] and [item["action"] for item in value["decisions"]] == ["adopt", "dispatch"]
    assert target.count == 1 and not value["resume_permitted"]
    request = approval(value)
    recorded = client.call("dag", {"operation": "approve_continuation", "request": request})
    assert target.count == 1
    assert client.call("dag", {"operation": "approve_continuation", "request": request}) == recorded
    result = run_dag(definition, batch_id=batch["batch_id"], recovery=request)
    assert result.succeeded, result.to_dict()
    assert target.count == 2
    with pytest.raises(AgentTaskError, match="consumed"):
        run_dag(definition, batch_id=batch["batch_id"], recovery=request)
    assert target.count == 2


def test_lookup_absence_never_turns_a_claimed_node_back_into_dispatch(service):
    client, _instance, target = service
    definition = graph()
    batch = client.call("dag", {"operation": "register", "request": {"definition": definition}})
    started = client.call("dag", {"operation": "begin", "request": {
        "batch_id": batch["batch_id"], "definition": definition, "max_parallel": 4}})
    client.call("dag", {"operation": "claim", "request": {
        "batch_id": batch["batch_id"], "attempt": started["attempt"], "node_id": "a"}})
    client.call("dag", {"operation": "pause_batch", "request": {"batch_id": batch["batch_id"]}})
    value = review(client, batch, definition)
    assert not value["can_approve"] and value["decisions"][0]["action"] == "wait"
    value["decisions"][0] = {"node_id": "a", "action": "dispatch", "spec": definition["nodes"][0]["task"]["spec"]}
    with pytest.raises(AgentTaskError, match="evidence or decisions changed"):
        client.call("dag", {"operation": "approve_continuation", "request": approval(value)})
    assert target.count == 0


@pytest.mark.parametrize("change", ["note", "graph", "decision", "snapshot"])
def test_reviewed_graph_or_decision_cannot_be_silently_changed(stopped, change):
    client, _instance, target, batch, definition = stopped
    request = approval(review(client, batch, definition))
    if change == "note":
        request["note"] = " "
    elif change == "graph":
        request["definition"]["nodes"][1]["depends_on"] = []
    elif change == "decision":
        request["decisions"][1]["spec"]["goal"] = "A different plan"
    else:
        request["snapshot"] = "0" * 64
    with pytest.raises(AgentTaskError):
        client.call("dag", {"operation": "approve_continuation", "request": request})
    assert target.count == 1


def test_fencing_invalidates_old_attempt_and_cancels_unconsumed_approval(stopped):
    client, _instance, target, batch, definition = stopped
    request = approval(review(client, batch, definition))
    approved = client.call("dag", {"operation": "approve_continuation", "request": request})
    client.call("dag", {"operation": "pause_batch", "request": {"batch_id": batch["batch_id"]}})
    with pytest.raises(AgentTaskError, match="consumed or cancelled"):
        client.call("dag", {"operation": "start_continuation", "request": {
            "batch_id": batch["batch_id"], "definition": definition, "approval_id": approved["approval_id"],
            "max_parallel": 4}})
    assert target.count == 1


def test_approval_transaction_rolls_back_all_bindings_and_adoptions(stopped):
    client, instance, target, batch, definition = stopped
    request = approval(review(client, batch, definition))
    with instance.runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER fail_binding BEFORE INSERT ON agent_dag_bindings "
                           "BEGIN SELECT RAISE(ABORT, 'fixture rollback'); END")
    with pytest.raises(AgentTaskError, match="database operation failed"):
        client.call("dag", {"operation": "approve_continuation", "request": request})
    with instance.runtime.store.connection(write=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_dag_approvals").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM agent_dag_adoptions").fetchone()[0] == 0
        connection.execute("DROP TRIGGER fail_binding")
    assert run_dag(definition, batch_id=batch["batch_id"], recovery=request).succeeded
    assert target.count == 2


def test_successor_adoption_uses_real_recovery_provenance_and_fresh_completion(service, monkeypatch):
    client, instance, target = service
    start = Mock()
    monkeypatch.setattr(instance.runtime.background, "start", start)
    definition = graph()
    definition["nodes"][0]["task"]["spec"]["actions"] *= 2
    batch = client.call("dag", {"operation": "register", "request": {"definition": definition}})
    begun = client.call("dag", {"operation": "begin", "request": {
        "batch_id": batch["batch_id"], "definition": definition, "max_parallel": 4}})
    client.call("dag", {"operation": "claim", "request": {
        "batch_id": batch["batch_id"], "attempt": begun["attempt"], "node_id": "a"}})
    task = begun["definition"]["nodes"][0]["task"]
    original = client.call("submit", {"spec": task["spec"], "idempotency_key": task["idempotency_key"]})["task_id"]
    frame = client.call("observe", {"task_id": original})
    client.call("act", {"task_id": original, "action": {"tool": "AC_increment",
                                                        "observation_id": frame["observation_id"]}})
    client.call("pause", {"task_id": original})
    client.call("dag", {"operation": "pause_batch", "request": {"batch_id": batch["batch_id"]}})
    remaining = client.call("recovery", {"operation": "preview", "request": {"task_id": original}})
    child = client.call("recovery", {"operation": "create", "request": {"task_id": original,
        "snapshot": remaining["snapshot"], "spec": remaining["draft"], "note": "Reviewed remaining action"}})["task_id"]
    assert run_task(instance.runtime, child).state == "succeeded"
    value = review(client, batch, definition)
    value["decisions"][0] = {"node_id": "a", "action": "successor", "task_id": child}
    value = review(client, batch, definition, decisions=value["decisions"])
    assert value["can_approve"]
    request = approval(value)
    approved = client.call("dag", {"operation": "approve_continuation", "request": request})
    begun = client.call("dag", {"operation": "start_continuation", "request": {
        "batch_id": batch["batch_id"], "definition": definition, "approval_id": approved["approval_id"],
        "max_parallel": 4}})
    result = client.call("dag", {"operation": "validate_node", "request": {
        "batch_id": batch["batch_id"], "attempt": begun["attempt"], "node_id": "a"}})
    assert result["task_id"] == child and target.count == 2
    unrelated = instance.runtime.submit(graph()["nodes"][1]["task"]["spec"])
    assert run_task(instance.runtime, unrelated.task_id).state == "succeeded"
    client.call("dag", {"operation": "pause_batch", "request": {"batch_id": batch["batch_id"]}})
    value = review(client, batch, definition)
    value["decisions"][0] = {"node_id": "a", "action": "successor", "task_id": unrelated.task_id}
    value = review(client, batch, definition, decisions=value["decisions"])
    assert not value["can_approve"] and target.count == 3


def test_expired_origin_can_be_replaced_only_for_never_dispatched_scoped_work(service, monkeypatch, tmp_path):
    client, instance, target = service
    allowed = tmp_path / "data"
    narrow = allowed / "reports"
    narrow.mkdir(parents=True)
    old, current = PathPolicy([allowed]), PathPolicy([narrow])
    old_id, current_id = old.managed_origin(), current.managed_origin()
    definition = graph()
    for node in definition["nodes"]:
        node["task"]["spec"]["roots"] = [str(allowed)]
    stop = threading.Event()
    original_call = AgentRuntimeClient.call

    def after_first(self, operation, body=None, **kwargs):
        result = original_call(self, operation, body, **kwargs)
        if operation == "dag" and body.get("operation") == "record" and body["request"]["node_id"] == "a":
            stop.set()
        return result

    monkeypatch.setattr(AgentRuntimeClient, "call", after_first)
    with origin_scope(old_id):
        batch = client.call("dag", {"operation": "register", "request": {"definition": definition}})
        assert not run_dag(definition, batch_id=batch["batch_id"], stop_event=stop).succeeded
    old.revoke_managed_origin()
    with origin_scope(current_id):
        value = review(client, batch, definition)
        assert value["can_approve"]
        assert value["decisions"][1]["spec"]["roots"] == [str(narrow)]
        assert value["decisions"][1]["spec"]["options"]["origin_policies"] == [current_id]
        result = run_dag(definition, batch_id=batch["batch_id"], recovery=approval(value))
        assert result.succeeded, result.to_dict()
        child = instance.runtime.store.get(result.nodes["b"].result["task_id"])
        assert child["spec"]["roots"] == [str(narrow)] and target.count == 2
