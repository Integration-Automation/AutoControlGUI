"""Real loopback HTTP integration over fake applications, without native capture or input."""
import json

import pytest

from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


class Counter:
    """A minimal target for authenticated transport tests."""

    def __init__(self):
        self.value = 0

    def ready(self, _spec):
        return True, ""

    def observe(self):
        return {"identity": "counter", "value": self.value}

    def perform(self, _name, _args):
        self.value += 1
        return {"value": self.value}

    def cleanup(self):
        return None


@pytest.fixture
def service(tmp_path):
    instance = AgentRuntimeService(tmp_path, targets={"counter": Counter()})
    instance.start()
    yield AgentRuntimeClient(tmp_path / "agent_runtime.json"), instance
    instance.close()


def spec():
    return {"goal": "count", "target": "counter", "allowed_tools": ["AC_increment"],
            "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}]}


def test_service_round_trip_preserves_raw_results(service):
    client, _instance = service
    task = client.call("submit", {"spec": spec()})
    frame = client.call("observe", {"task_id": task["task_id"]})
    action = {"tool": "AC_increment", "observation_id": frame["observation_id"]}
    result = client.call("act", {"task_id": task["task_id"], "action": action})
    assert result["result"] == {"value": 1}
    assert client.call("finish", {"task_id": task["task_id"]})["state"] == "succeeded"


def test_bridge_keeps_owner_identity(service):
    client, instance = service
    with authorization_scope(AuthorizationContext("alice", "operator")):
        task = client.call("submit", {"spec": spec()})
    assert instance.runtime.store.get(task["task_id"])["owner"]["user_id"] == "alice"
    with authorization_scope(AuthorizationContext("bob", "operator")):
        assert client.call("list")["tasks"] == []
        with pytest.raises(AgentTaskError):
            client.call("get", {"task_id": task["task_id"]})


def test_emergency_stop_keeps_other_principals_tasks(service):
    client, instance = service
    with authorization_scope(AuthorizationContext("alice", "operator")):
        left = client.call("submit", {"spec": spec()})
    with authorization_scope(AuthorizationContext("bob", "operator")):
        right = client.call("submit", {"spec": spec()})
        result = client.call("stop_all", {})
    assert {task["task_id"] for task in result["tasks"]} == {right["task_id"]}
    assert instance.runtime.get(left["task_id"]).state == "queued"
    assert instance.runtime.get(right["task_id"]).state == "cancelled"


def test_viewer_cannot_become_local_operator(service):
    client, instance = service
    with authorization_scope(AuthorizationContext("reader", "viewer")):
        with pytest.raises(AgentTaskError):
            client.call("submit", {"spec": spec()})
    assert instance.runtime.list() == []


def test_status_contains_no_credential(service):
    _client, instance = service
    metadata = json.loads((instance.directory / "agent_runtime.json").read_text(encoding="utf-8"))
    assert metadata["token"] not in json.dumps(instance.status())


def test_abandoned_external_lease_expires_without_another_client_request(service):
    import time
    client, instance = service
    task = client.call("submit", {"spec": {**spec(), "budget": {"wall_seconds": 1}}})
    client.call("observe", {"task_id": task["task_id"]})
    deadline = time.monotonic() + 4
    while instance.runtime.get(task["task_id"]).state != "timed_out" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert instance.runtime.get(task["task_id"]).state == "timed_out"
    assert not instance.runtime._leases


def test_second_runtime_cannot_recover_live_tasks(service):
    _client, instance = service
    with pytest.raises(AgentTaskError, match="owns"):
        AgentRuntimeService(instance.directory, targets={"counter": Counter()})


def test_internal_skill_runs_after_submission(service):
    import time
    client, _instance = service
    specification = {**spec(), "mode": "skill", "actions": [{"tool": "AC_increment"}]}
    task = client.call("submit", {"spec": specification})
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = client.call("get", {"task_id": task["task_id"]})
        if status["state"] == "succeeded":
            break
        time.sleep(0.05)
    assert status["state"] == "succeeded"


def test_operator_cannot_stop_host_service(service):
    client, instance = service
    with authorization_scope(AuthorizationContext("alice", "operator")):
        with pytest.raises(AgentTaskError):
            client.call("shutdown", {})
    assert not instance.runtime.shutdown_requested.is_set()
