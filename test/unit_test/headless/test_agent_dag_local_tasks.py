"""Cross-owner local DAG work uses original ownership and independently revocable admitting authority."""
import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.dag_batch_recording import bound_node
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from je_auto_control.utils.rbac.users import UserStore
from je_auto_control.utils.dag import run_dag
from .test_agent_dag_batch_loopback import service as service
from .test_agent_dag_batches import graph
from .test_agent_dag_background import until


@pytest.fixture
def owned(service, tmp_path):
    client, instance, target = service
    users = UserStore(tmp_path / "users.json")
    users.add_user(user_id="owner", display_name="Owner", role="operator")
    users.add_user(user_id="reviewer", display_name="Reviewer", role="admin")
    owner = AuthorizationContext("owner", "operator", store_path=str(users.path))
    actor = AuthorizationContext("reviewer", "admin", store_path=str(users.path))
    with authorization_scope(owner):
        batch = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
    return client, instance, target, users, owner, actor, batch


def begin(owned):
    client, instance, _target, _users, _owner, actor, batch = owned
    with authorization_scope(actor):
        started = client.call("dag", {"operation": "begin", "request": {
            "batch_id": batch["batch_id"], "definition": graph(), "max_parallel": 4}})
        client.call("dag", {"operation": "claim", "request": {
            "batch_id": batch["batch_id"], "attempt": started["attempt"], "node_id": "a"}})
        node = bound_node(instance.runtime.batches._row(batch["batch_id"]), "a")
    return started, node


def local(owned, started, operation, body, **fields):
    client, _instance, _target, _users, _owner, actor, batch = owned
    with authorization_scope(actor):
        return client.call("dag", {"operation": "local_task", "request": {
            "batch_id": batch["batch_id"], "attempt": started["attempt"], "node_id": "a",
            "operation": operation, "body": body, **fields}})


def submission(node):
    return {"spec": node["task"]["spec"], "idempotency_key": node["task"]["idempotency_key"]}


def test_admin_caller_executes_all_nodes_under_original_owner_and_records_actual_actor(owned):
    _client, instance, target, _users, _owner, actor, batch = owned
    with authorization_scope(actor):
        result = run_dag(graph(), batch_id=batch["batch_id"])
    assert result.succeeded, result.to_dict()
    assert target.count == 2
    for node in result.nodes.values():
        task_id = node.result["task_id"]
        assert instance.runtime.store.get(task_id)["owner"]["user_id"] == "owner"
        with instance.runtime.store.connection() as connection:
            row = connection.execute("SELECT actor FROM agent_dag_local_tasks WHERE task_id=?", (task_id,)).fetchone()
        assert json.loads(row["actor"])["user_id"] == "reviewer"
        visible = instance.runtime.get(task_id).metadata["local_dag_admission"]
        assert visible["actor"] == "reviewer" and visible["contract"] == 1
        assert "store_path" not in visible and "attempt" not in visible


def test_local_admission_is_idempotent_and_cannot_bind_an_unrelated_task(owned, monkeypatch):
    _client, instance, target, _users, _owner, _actor, _batch = owned
    started, node = begin(owned)
    monkeypatch.setattr(instance.runtime.background, "start", Mock())
    first = local(owned, started, "submit", submission(node))
    assert local(owned, started, "submit", submission(node)) == first
    with pytest.raises(AgentTaskError, match="identity or admitting actor"):
        local(owned, started, "get", {"task_id": "unrelated-task"})
    assert len(instance.runtime.list()) == 1 and target.count == 0


@pytest.mark.parametrize("fault", ["goal", "key", "extra", "operation", "task_id"])
def test_local_transport_rejects_changed_contracts_and_unbounded_operations(owned, fault):
    _client, instance, target, _users, _owner, _actor, _batch = owned
    started, node = begin(owned)
    body = deepcopy(submission(node))
    operation = "submit"
    if fault == "goal":
        body["spec"]["goal"] = "unreviewed task"
    elif fault == "key":
        body["idempotency_key"] = "unrelated"
    elif fault == "extra":
        body["actor"] = {"user_id": "invented", "role": "admin"}
    elif fault == "operation":
        operation = ["submit"]
    else:
        operation, body = "get", {"task_id": []}
    with pytest.raises(AgentTaskError):
        local(owned, started, operation, body)
    assert instance.runtime.list() == [] and target.count == 0


def test_preexisting_request_without_admission_witness_is_never_backfilled(owned, monkeypatch):
    _client, instance, target, _users, owner, _actor, _batch = owned
    started, node = begin(owned)
    monkeypatch.setattr(instance.runtime.background, "start", Mock())
    with authorization_scope(owner):
        task = instance.runtime.submit(node["task"]["spec"], idempotency_key=node["task"]["idempotency_key"])
    with pytest.raises(AgentTaskError, match="trusted admission evidence"):
        local(owned, started, "submit", submission(node))
    with instance.runtime.store.connection() as connection:
        assert connection.execute("SELECT 1 FROM agent_dag_local_tasks WHERE task_id=?",
                                  (task.task_id,)).fetchone() is None
    assert target.count == 0 and len(instance.runtime.list()) == 1


def test_admission_failure_rolls_back_task_key_and_both_witnesses(owned, monkeypatch):
    _client, instance, target, _users, _owner, _actor, _batch = owned
    started, node = begin(owned)
    start = Mock()
    monkeypatch.setattr(instance.runtime.background, "start", start)
    with instance.runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER fail_dag_admission BEFORE INSERT ON agent_dag_local_tasks "
                           "BEGIN SELECT RAISE(ABORT,'fixture rollback'); END")
    with pytest.raises(AgentTaskError, match="database operation failed"):
        local(owned, started, "submit", submission(node))
    with instance.runtime.store.connection() as connection:
        for table in ("agent_tasks", "agent_request_keys", "agent_task_submissions", "agent_dag_local_tasks"):
            assert connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
    start.assert_not_called()
    assert target.count == 0


@pytest.mark.parametrize("revoked,role", [("owner", "viewer"), ("reviewer", "viewer"), ("reviewer", "operator")])
def test_queued_admitted_task_revalidates_both_principals_before_input(owned, monkeypatch, revoked, role):
    _client, instance, target, users, _owner, _actor, _batch = owned
    started, node = begin(owned)
    original = instance.runtime.background.start
    monkeypatch.setattr(instance.runtime.background, "start", Mock())
    task = local(owned, started, "submit", submission(node))
    users.set_role(revoked, role)
    original(task["task_id"])
    until(lambda: instance.runtime.get(task["task_id"]).state != "queued")
    assert instance.runtime.get(task["task_id"]).state in {"waiting_user", "cancelled", "paused"}
    assert target.count == 0


def test_fenced_attempt_can_retire_only_its_admitted_task_after_original_owner_loses_input(owned, monkeypatch):
    client, instance, target, users, _owner, actor, batch = owned
    started, node = begin(owned)
    monkeypatch.setattr(instance.runtime.background, "start", Mock())
    task = local(owned, started, "submit", submission(node))
    users.set_role("owner", "viewer")
    with authorization_scope(actor):
        client.call("dag", {"operation": "pause_batch", "request": {"batch_id": batch["batch_id"]}})
    paused = local(owned, started, "pause", {"task_id": task["task_id"]})
    assert paused["state"] == "paused" and paused["metadata"]["input_released"] is True and target.count == 0


def test_maintenance_retires_lease_when_admin_loses_cross_owner_authority(owned, monkeypatch):
    _client, instance, target, users, owner, _actor, _batch = owned
    started, node = begin(owned)
    monkeypatch.setattr(instance.runtime.background, "start", Mock())
    task = local(owned, started, "submit", submission(node))
    with authorization_scope(owner):
        instance.runtime.observe(task["task_id"])
    users.set_role("reviewer", "operator")
    instance.runtime.maintain()
    result = instance.runtime.get(task["task_id"])
    assert result.state == "cancelled" and result.metadata["input_released"] is True and target.count == 0


def test_revocation_during_grounding_is_refused_before_the_target_input_call(owned, monkeypatch):
    _client, instance, target, users, owner, _actor, _batch = owned
    started, node = begin(owned)
    monkeypatch.setattr(instance.runtime.background, "start", Mock())
    task = local(owned, started, "submit", submission(node))
    original = target.observe

    def revoke_during_grounding():
        observation = original()
        users.set_role("reviewer", "operator")
        return observation

    with authorization_scope(owner):
        frame = instance.runtime.observe(task["task_id"])
        monkeypatch.setattr(target, "observe", revoke_during_grounding)
        with pytest.raises(AuthorizationError):
            instance.runtime.act(task["task_id"], {"tool": "AC_increment", "observation_id": frame.observation_id})
    receipts = instance.runtime.store.actions(task["task_id"])
    assert target.count == 0 and [item["status"] for item in receipts] == ["failed"]
