"""Real local/remote HTTP task DAGs use fake targets and owned ephemeral services only."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from headless.test_dag_managed_tasks import task
from je_auto_control.utils.agent_runtime import origin_policy
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.admin.admin_client import AdminConsoleClient
from je_auto_control.utils.dag import run_dag
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


class Target:
    def __init__(self, barrier=None):
        self.count = 0
        self.barrier = barrier

    def ready(self, _spec):
        return True, ""

    def observe(self):
        return {"identity": "fixture"}

    def perform(self, _tool, _arguments):
        if self.barrier is not None:
            self.barrier.wait(timeout=4)
        self.count += 1
        return {"value": 1}

    def cleanup(self):
        return None


def test_two_host_dag_deduplicates_and_keeps_local_principal_and_witnesses_local(tmp_path, monkeypatch):
    from je_auto_control.utils.admin import admin_client
    from je_auto_control.utils.agent_runtime import client as client_module

    monkeypatch.setattr(origin_policy, "_directory", lambda: tmp_path / "origins")
    witness = origin_policy.OriginWitness((tmp_path,))
    store = UserStore(tmp_path / "users.json")
    store.add_user(user_id="local-admin", display_name="Local", role="admin")
    local_target, remote_target = Target(), Target()
    local = AgentRuntimeService(tmp_path / "local", targets={"fixture": local_target})
    remote = AgentRuntimeService(tmp_path / "remote", targets={"fixture": remote_target})
    try:
        local.start()
        remote.start()
        local_client = AgentRuntimeClient(local.directory / "agent_runtime.json")
        monkeypatch.setattr(client_module, "AgentRuntimeClient", lambda: local_client)
        metadata = json.loads((remote.directory / "agent_runtime.json").read_text())
        console = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
        console.add_host("reviewed-remote", metadata["url"], metadata["token"])
        monkeypatch.setattr(admin_client, "default_admin_console", lambda: console)
        graph = {"nodes": [
            {"id": "local", "task": task(idempotency_key="reviewed-local")},
            {"id": "remote", "host": "reviewed-remote", "depends_on": ["local"],
             "task": task(idempotency_key="reviewed-remote")},
        ]}
        owner = AuthorizationContext("local-admin", "admin", store_path=str(store.path))
        with authorization_scope(owner), origin_policy.origin_scope(witness.identifier):
            first = run_dag(graph)
            repeated = run_dag(graph)
        assert first.succeeded, first.to_dict()
        assert repeated.succeeded, repeated.to_dict()
        assert local_target.count == remote_target.count == 1
        local_id = first.nodes["local"].result["task_id"]
        remote_id = first.nodes["remote"].result["task_id"]
        assert repeated.nodes["local"].result["task_id"] == local_id
        assert repeated.nodes["remote"].result["task_id"] == remote_id
        local_row, remote_row = local.runtime.store.get(local_id), remote.runtime.store.get(remote_id)
        assert local_row["owner"]["user_id"] == "local-admin"
        assert local_row["spec"]["options"]["origin_policies"] == [witness.identifier]
        assert remote_row["owner"] == {}
        assert "origin_policies" not in remote_row["spec"]["options"]
        assert str(store.path) not in str(remote_row)
        assert witness.identifier not in str(remote_row)
        assert not local.runtime._leases and not remote.runtime._leases
    finally:
        local.close()
        remote.close()


def test_distinct_targets_run_concurrently_with_destination_verification(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import client as client_module

    barrier = threading.Barrier(2)
    left, right = Target(barrier), Target(barrier)
    service = AgentRuntimeService(tmp_path / "service", targets={"left": left, "right": right})
    try:
        service.start()
        client = AgentRuntimeClient(service.directory / "agent_runtime.json")
        monkeypatch.setattr(client_module, "AgentRuntimeClient", lambda: client)
        graph = {"nodes": []}
        for name in ("left", "right"):
            payload = task(idempotency_key=name, wait_seconds=10)
            payload["spec"]["target"] = name
            graph["nodes"].append({"id": name, "task": payload})
        result = run_dag(graph, max_parallel=2)
        assert result.succeeded, result.to_dict()
        assert left.count == right.count == 1
        assert not service.runtime._leases
    finally:
        service.close()


def test_same_target_queued_node_cannot_overlap_input(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import client as client_module

    entered, release = threading.Event(), threading.Event()

    class HeldTarget(Target):
        def perform(self, tool, arguments):
            entered.set()
            assert release.wait(4)
            return super().perform(tool, arguments)

    target = HeldTarget()
    service = AgentRuntimeService(tmp_path / "service", targets={"fixture": target})
    try:
        service.start()
        client = AgentRuntimeClient(service.directory / "agent_runtime.json")
        monkeypatch.setattr(client_module, "AgentRuntimeClient", lambda: client)
        graph = {"nodes": [{"id": name, "task": task(idempotency_key=name, wait_seconds=10)}
                           for name in ("left", "right")]}
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_dag, graph)
            try:
                assert entered.wait(4)
                assert len(service.runtime._leases) == 1
                assert target.count == 0
            finally:
                release.set()
            result = future.result(timeout=12)
        assert result.succeeded, result.to_dict()
        assert target.count == 2
    finally:
        release.set()
        service.close()
