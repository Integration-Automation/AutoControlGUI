"""Stale approval, dependency loss, replay and admission transaction guards use owned services only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.submission import submitted_digest
from je_auto_control.utils.agent_runtime.retention import _remove_metadata
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from .test_agent_dag_batch_loopback import service as service
from .test_agent_dag_continuation import stopped as stopped, review, approval


def approve(client, batch, definition):
    request = approval(review(client, batch, definition))
    recorded = client.call("dag", {"operation": "approve_continuation", "request": request})
    return request, recorded


def start(client, batch, definition, recorded):
    return client.call("dag", {"operation": "start_continuation", "request": {
        "batch_id": batch["batch_id"], "definition": definition, "approval_id": recorded["approval_id"],
        "max_parallel": 4}})


def test_destination_retention_after_approval_prevents_start(stopped):
    client, instance, target, batch, definition = stopped
    request, recorded = approve(client, batch, definition)
    _remove_metadata(instance.runtime.store, request["decisions"][0]["task_id"])
    with pytest.raises(AgentTaskError, match="evidence changed"):
        start(client, batch, definition, recorded)
    assert target.count == 1


def test_lost_adoption_evidence_after_start_cannot_publish_false_batch_success(stopped):
    client, instance, target, batch, definition = stopped
    request, recorded = approve(client, batch, definition)
    started = start(client, batch, definition, recorded)
    _remove_metadata(instance.runtime.store, request["decisions"][0]["task_id"])
    with pytest.raises(AgentTaskError, match="source identity"):
        client.call("dag", {"operation": "validate_node", "request": {
            "batch_id": batch["batch_id"], "attempt": started["attempt"], "node_id": "a"}})
    finished = client.call("dag", {"operation": "finish", "request": {
        "batch_id": batch["batch_id"], "attempt": started["attempt"]}})
    assert finished["state"] == "waiting_review" and finished["nodes"][0]["phase"] == "unknown"
    assert target.count == 1


def test_only_one_concurrent_caller_can_consume_approval(stopped):
    client, _instance, target, batch, definition = stopped
    _request, recorded = approve(client, batch, definition)
    barrier = Barrier(2)

    def consume(_index):
        barrier.wait(timeout=10)
        try:
            return start(client, batch, definition, recorded)["attempt"]
        except AgentTaskError:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(consume, (0, 1)))
    assert sum(value is not None for value in results) == 1 and target.count == 1


def test_another_admin_cannot_reuse_an_actors_review_and_audit_keeps_the_real_actor(stopped):
    client, _instance, target, batch, definition = stopped
    request = approval(review(client, batch, definition))
    with authorization_scope(AuthorizationContext("reviewer", "admin")):
        with pytest.raises(AgentTaskError, match="evidence or decisions changed"):
            client.call("dag", {"operation": "approve_continuation", "request": request})
        approve(client, batch, definition)
        current = client.call("dag", {"operation": "get", "request": {"batch_id": batch["batch_id"]}})
    assert current["continuations"][0]["actor"] == "reviewer"
    assert current["continuations"][0]["note"] and target.count == 1


@pytest.mark.parametrize("fault", ["missing", "duplicate", "unknown", "extra", "null"])
def test_closed_whole_graph_decisions_cannot_omit_or_invent_nodes(stopped, fault):
    client, _instance, target, batch, definition = stopped
    request = approval(review(client, batch, definition))
    if fault == "missing":
        request["decisions"].pop()
    elif fault == "duplicate":
        request["decisions"][1] = request["decisions"][0]
    elif fault == "unknown":
        request["decisions"][1]["node_id"] = "unregistered-node"
    elif fault == "null":
        request["decisions"] = None
    else:
        request["decisions"][0]["resume"] = True
    with pytest.raises(AgentTaskError):
        client.call("dag", {"operation": "approve_continuation", "request": request})
    assert target.count == 1


def test_tagged_submission_witness_is_atomic_and_legacy_retries_never_backfill(service):
    _client, instance, _target = service
    data = {"goal": "tagged fixture", "target": "fixture", "mode": "skill", "allowed_tools": ["AC_increment"],
            "actions": [{"tool": "AC_increment"}],
            "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}],
            "options": {"dag_batch": {"batch_id": "fixture", "node_id": "a", "graph_hash": "0" * 64}}}
    with instance.runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER fail_admission BEFORE INSERT ON agent_task_submissions "
                           "BEGIN SELECT RAISE(ABORT, 'fixture rollback'); END")
    with pytest.raises(AgentTaskError, match="database operation failed"):
        instance.runtime.submit(data, idempotency_key="tagged")
    with instance.runtime.store.connection(write=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_tasks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM agent_request_keys").fetchone()[0] == 0
        connection.execute("DROP TRIGGER fail_admission")
    task = instance.runtime.submit(data, idempotency_key="tagged")
    metadata = instance.runtime.get(task.task_id).metadata
    assert metadata["submission_contract"] == 1 and metadata["submitted_spec_digest"] == submitted_digest(data)
    legacy = instance.runtime._create_task(instance.runtime._validated_spec(data), "legacy-tagged")
    assert instance.runtime.submit(data, idempotency_key="legacy-tagged").task_id == legacy.task_id
    assert "submission_contract" not in instance.runtime.get(legacy.task_id).metadata


def test_fencing_a_started_continuation_rejects_its_next_claim(stopped):
    client, _instance, target, batch, definition = stopped
    _request, recorded = approve(client, batch, definition)
    started = start(client, batch, definition, recorded)
    client.call("dag", {"operation": "pause_batch", "request": {"batch_id": batch["batch_id"]}})
    with pytest.raises(AgentTaskError, match="inactive"):
        client.call("dag", {"operation": "claim", "request": {
            "batch_id": batch["batch_id"], "attempt": started["attempt"], "node_id": "b"}})
    current = client.call("dag", {"operation": "get", "request": {"batch_id": batch["batch_id"]}})
    assert current["nodes"][1]["phase"] == "pending" and target.count == 1
