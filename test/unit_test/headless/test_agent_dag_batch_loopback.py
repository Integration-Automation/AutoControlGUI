"""Durable batch coordination over real owned HTTP services and fake application targets."""
import threading

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.dag import run_dag, managed_tasks
from .test_agent_dag_batches import graph


class Target:
    def __init__(self):
        self.count = 0
        self.performed = threading.Event()

    def ready(self, _spec):
        return True, ""

    def observe(self):
        return {"identity": "fixture"}

    def perform(self, _tool, _arguments):
        self.count += 1
        self.performed.set()
        return {"value": 1}

    def cleanup(self):
        return None


@pytest.fixture
def service(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import client as client_module
    target = Target()
    instance = AgentRuntimeService(tmp_path, targets={"fixture": target})
    try:
        instance.start()
        path = instance.directory / "agent_runtime.json"
        monkeypatch.setattr(client_module, "default_connection_path", lambda: path)
        yield AgentRuntimeClient(path), instance, target
    finally:
        instance.close()


def test_bound_graph_executes_once_and_independent_receipts_release_dependencies(service):
    client, instance, target = service
    definition = graph()
    registered = client.call("dag", {"operation": "register", "request": {"definition": definition}})
    assert target.count == 0
    result = run_dag(definition, batch_id=registered["batch_id"])
    assert result.succeeded, result.to_dict()
    batch = client.call("dag", {"operation": "get", "request": {"batch_id": registered["batch_id"]}})
    assert batch["state"] == "succeeded" and target.count == 2
    assert all(node["phase"] == "confirmed" for node in batch["nodes"])
    for node in batch["nodes"]:
        task = instance.runtime.store.get(node["receipt"]["task_id"])
        assert task["spec"]["options"]["dag_batch"] == {
            "batch_id": registered["batch_id"], "graph_hash": registered["graph_hash"], "node_id": node["id"]}
    with pytest.raises(AgentTaskError, match="explicit recovery"):
        run_dag(definition, batch_id=registered["batch_id"])
    assert target.count == 2


def test_lost_submit_reply_remains_claimed_or_unknown_and_cannot_replay(service, monkeypatch):
    client, _instance, target = service
    registered = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
    original = managed_tasks._connection

    def connection(host):
        call = original(host)

        def lost_reply(operation, body, timeout):
            result = call(operation, body, timeout)
            if operation == "submit":
                assert target.performed.wait(5)
                raise AgentTaskError("fixture lost reply after durable acceptance")
            return result

        return lost_reply

    monkeypatch.setattr(managed_tasks, "_connection", connection)
    result = run_dag(graph(), batch_id=registered["batch_id"])
    assert not result.succeeded and target.performed.wait(5)
    batch = client.call("dag", {"operation": "get", "request": {"batch_id": registered["batch_id"]}})
    assert batch["state"] == "waiting_review"
    assert [node["phase"] for node in batch["nodes"]] == ["unknown", "pending"]
    with pytest.raises(AgentTaskError, match="explicit recovery"):
        run_dag(graph(), batch_id=registered["batch_id"])
    assert target.count == 1


def test_two_host_batch_tags_match_without_forwarding_local_principal_or_origins(service, tmp_path, monkeypatch):
    import json
    from je_auto_control.utils.admin import admin_client
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
    from je_auto_control.utils.agent_runtime import origin_policy
    client, local, local_target = service
    remote_target = Target()
    remote = AgentRuntimeService(tmp_path / "remote", targets={"fixture": remote_target})
    monkeypatch.setattr(origin_policy, "_directory", lambda: tmp_path / "origins")
    witness = origin_policy.OriginWitness((tmp_path,))
    try:
        remote.start()
        metadata = json.loads((remote.directory / "agent_runtime.json").read_text())
        console = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
        console.add_host("remote-fixture", metadata["url"], metadata["token"])
        monkeypatch.setattr(admin_client, "default_admin_console", lambda: console)
        definition = graph()
        definition["nodes"][1]["host"] = "remote-fixture"
        owner = AuthorizationContext("local-admin", "admin")
        with authorization_scope(owner), origin_policy.origin_scope(witness.identifier):
            registered = client.call("dag", {"operation": "register", "request": {"definition": definition}})
            result = run_dag(definition, batch_id=registered["batch_id"])
            assert result.succeeded, result.to_dict()
            saved = client.call("dag", {"operation": "get", "request": {"batch_id": registered["batch_id"]}})
        assert local_target.count == remote_target.count == 1
        assert metadata["token"] not in str(saved)
        remote_row = remote.runtime.store.get(result.nodes["b"].result["task_id"])
        local_row = local.runtime.store.get(result.nodes["a"].result["task_id"])
        assert remote_row["owner"] == {} and local_row["owner"]["user_id"] == "local-admin"
        assert "origin_policies" not in remote_row["spec"]["options"]
        assert remote_row["spec"]["options"]["dag_batch"]["batch_id"] == registered["batch_id"]
    finally:
        remote.close()
