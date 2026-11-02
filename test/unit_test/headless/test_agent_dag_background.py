"""Owned services coordinate durable batches independently of clients, default paths and GUI workers."""
import json
import threading
import time
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore
from .test_agent_dag_batch_loopback import service as service, Target
from .test_agent_dag_batches import graph
from .test_agent_dag_continuation import stopped as stopped, review, approval


def until(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        threading.Event().wait(0.02)
    pytest.fail("owned background batch did not reach its expected state")


def read(instance, batch):
    return instance.runtime.batches.control("get", {"batch_id": batch["batch_id"]})


def submit(client, batch, definition, **fields):
    return client.call("dag", {"operation": "run_background", "request": {
        "batch_id": batch["batch_id"], "definition": definition,
        "max_parallel": batch["max_parallel"], **fields}})


def finished(instance, batch):
    record = read(instance, batch)
    return record if record["background"]["state"] in {"success", "failed"} else None


def test_service_runs_without_any_default_client_connection_file(service, monkeypatch, tmp_path):
    client, instance, target = service
    definition = graph()
    batch = client.call("dag", {"operation": "register", "request": {
        "definition": definition, "max_parallel": 2}})
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.client.default_connection_path",
                        lambda: tmp_path / "missing-global-connection.json")
    accepted = submit(client, batch, definition)
    assert accepted["background"]["state"] in {"new", "in_progress", "success"}
    result = until(lambda: finished(instance, batch))
    assert result["state"] == "succeeded" and result["background"]["state"] == "success"
    assert target.count == 2 and all(node["phase"] == "confirmed" for node in result["nodes"])
    with instance.runtime.store.connection() as connection:
        data = json.loads(connection.execute("SELECT data FROM work_items WHERE queue='agent_dag'").fetchone()[0])
    assert data["started"]["max_parallel"] == 2
    with pytest.raises(AgentTaskError, match="already started"):
        submit(client, batch, definition)
    assert target.count == 2


def test_admin_dispatch_refreshes_actor_but_destination_tasks_belong_to_original_owner(service):
    client, instance, target = service
    with authorization_scope(AuthorizationContext("alice", "operator")):
        batch = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
    with authorization_scope(AuthorizationContext("reviewer", "admin")):
        submit(client, batch, graph())
        result = until(lambda: finished(instance, batch))
    assert result["state"] == "succeeded" and target.count == 2
    for node in result["nodes"]:
        assert instance.runtime.store.get(node["receipt"]["task_id"])["owner"]["user_id"] == "alice"


def test_approved_continuation_runs_in_background_without_redispatching_completed_parent(stopped):
    client, instance, target, batch, definition = stopped
    request = approval(review(client, batch, definition))
    approved = client.call("dag", {"operation": "approve_continuation", "request": request})
    submit(client, batch, definition, approval_id=approved["approval_id"])
    result = until(lambda: finished(instance, batch))
    assert result["state"] == "succeeded" and target.count == 2
    assert result["continuations"][0]["state"] == "used"
    with pytest.raises(AgentTaskError, match="consumed"):
        submit(client, batch, definition, approval_id=approved["approval_id"])


def test_failed_queue_acceptance_fences_attempt_without_input(service, monkeypatch):
    client, instance, target = service
    batch = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
    monkeypatch.setattr(instance._dag_jobs.queue, "add", Mock(side_effect=AgentTaskError("fixture queue failure")))
    with pytest.raises(AgentTaskError, match="fixture queue failure"):
        submit(client, batch, graph())
    assert read(instance, batch)["state"] == "waiting_review" and target.count == 0


def test_background_requires_an_explicit_service_and_never_runs_on_import(tmp_path):
    instance = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": object()})
    try:
        batch = instance.batches.control("register", {"definition": graph()})
        with pytest.raises(AgentTaskError, match="explicitly started service"):
            instance.batches.control("run_background", {"batch_id": batch["batch_id"],
                "definition": graph(), "max_parallel": 4})
        assert instance.batches.control("get", {"batch_id": batch["batch_id"]})["state"] == "registered"
    finally:
        instance.close()


def test_shutdown_and_restart_do_not_replay_a_queued_delivery_or_reset_a_claim(service, monkeypatch):
    client, instance, target = service
    jobs = instance._dag_jobs
    monkeypatch.setattr(jobs, "_drain", lambda: jobs._stop.wait())
    batch = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
    submit(client, batch, graph())
    with instance.runtime.store.connection() as connection:
        data = json.loads(connection.execute("SELECT data FROM work_items WHERE queue='agent_dag'").fetchone()[0])
    instance.runtime.batches.control("claim", {"batch_id": batch["batch_id"],
        "attempt": data["started"]["attempt"], "node_id": "a"})
    instance.close()
    restarted = AgentRuntimeService(instance.directory, targets={"fixture": target})
    try:
        restarted.start()
        record = read(restarted, batch)
        assert record["state"] == "waiting_review" and record["background"]["state"] == "failed"
        assert record["nodes"][0]["phase"] == "claimed" and target.count == 0
        inspected = restarted.runtime.batches.control("review_continuation", {
            "batch_id": batch["batch_id"], "definition": graph()})
        assert not inspected["can_approve"] and target.count == 0
    finally:
        restarted.close()


@pytest.mark.parametrize("revoked", ["owner", "reviewer"])
def test_delayed_background_work_refreshes_both_owners_before_any_claim(service, monkeypatch, tmp_path, revoked):
    client, instance, target = service
    users = UserStore(tmp_path / "users.json")
    users.add_user(user_id="owner", display_name="Owner", role="operator")
    users.add_user(user_id="reviewer", display_name="Reviewer", role="admin")
    entered, proceed = threading.Event(), threading.Event()
    original = instance._dag_jobs._execute

    def delayed(worker):
        entered.set()
        assert proceed.wait(5)
        return original(worker)

    monkeypatch.setattr(instance._dag_jobs, "_execute", delayed)
    with authorization_scope(AuthorizationContext("owner", "operator", store_path=str(users.path))):
        batch = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
    try:
        with authorization_scope(AuthorizationContext("reviewer", "admin", store_path=str(users.path))):
            submit(client, batch, graph())
        assert entered.wait(5)
        users.set_role(revoked, "viewer")
        proceed.set()
        result = until(lambda: finished(instance, batch))
        assert result["state"] == "waiting_review" and target.count == 0
        assert all(node["phase"] == "pending" for node in result["nodes"])
    finally:
        proceed.set()


def test_stop_all_fences_accepted_coordinators_before_any_delayed_node_dispatch(service, monkeypatch):
    client, instance, target = service
    proceed, entered = threading.Event(), threading.Event()
    original = instance._dag_jobs._execute

    def delayed(worker):
        entered.set()
        assert proceed.wait(5)
        return original(worker)

    monkeypatch.setattr(instance._dag_jobs, "_execute", delayed)
    batch = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
    try:
        submit(client, batch, graph())
        assert entered.wait(5)
        client.call("stop_all", {})
        proceed.set()
        result = until(lambda: finished(instance, batch))
        assert result["state"] == "waiting_review" and target.count == 0
    finally:
        proceed.set()


def test_service_background_keeps_local_ownership_and_never_forwards_it_to_remote_hosts(service, monkeypatch, tmp_path):
    client, local, target = service
    remote_target = Target()
    remote = AgentRuntimeService(tmp_path / "remote", targets={"fixture": remote_target})
    try:
        remote.start()
        metadata = json.loads((remote.directory / "agent_runtime.json").read_text())
        monkeypatch.setattr("je_auto_control.utils.dag.managed_tasks._host_identity",
                            lambda _host: (metadata["url"], metadata["token"]))
        definition = graph()
        definition["nodes"][1]["host"] = "remote"
        with authorization_scope(AuthorizationContext("source-admin", "admin")):
            batch = client.call("dag", {"operation": "register", "request": {"definition": definition}})
            submit(client, batch, definition)
            result = until(lambda: finished(local, batch))
        assert result["state"] == "succeeded" and target.count == remote_target.count == 1
        local_row = local.runtime.store.get(result["nodes"][0]["receipt"]["task_id"])
        remote_row = remote.runtime.store.get(result["nodes"][1]["receipt"]["task_id"])
        assert local_row["owner"]["user_id"] == "source-admin" and remote_row["owner"] == {}
        assert "origin_policies" not in remote_row["spec"]["options"]
    finally:
        remote.close()
