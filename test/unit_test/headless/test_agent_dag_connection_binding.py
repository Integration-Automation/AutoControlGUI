"""A managed caller never redirects old coordination or local destinations to another runtime."""
import json

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.dag import run_dag
from .test_agent_dag_batch_loopback import service as service, Target
from .test_agent_dag_batches import graph
from .test_agent_dag_background import until


def test_default_connection_discovery_change_keeps_all_nodes_and_verification_on_source(service, monkeypatch, tmp_path):
    client, source, target = service
    other_target = Target()
    other = AgentRuntimeService(tmp_path / "other", targets={"fixture": other_target})
    original = AgentRuntimeClient.call

    def after_first_record(self, operation, body=None, **kwargs):
        reply = original(self, operation, body, **kwargs)
        if operation == "dag" and body.get("operation") == "record" and body["request"]["node_id"] == "a":
            monkeypatch.setattr("je_auto_control.utils.agent_runtime.client.default_connection_path",
                                lambda: other.directory / "agent_runtime.json")
        return reply

    try:
        other.start()
        batch = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
        monkeypatch.setattr(AgentRuntimeClient, "call", after_first_record)
        result = run_dag(graph(), batch_id=batch["batch_id"])
        assert result.succeeded, result.to_dict()
        assert target.count == 2 and other_target.count == 0 and other.runtime.list() == []
        assert source.runtime.batches.control("get", {"batch_id": batch["batch_id"]})["state"] == "succeeded"
    finally:
        other.close()


@pytest.mark.parametrize("replacement", ["service", "generation", "token"])
def test_replaced_owner_file_stops_future_dispatch_and_never_sends_control_to_replacement(
        service, monkeypatch, tmp_path, replacement):
    client, source, target = service
    other_target = Target()
    other = AgentRuntimeService(tmp_path / "other", targets={"fixture": other_target})
    path = source.directory / "agent_runtime.json"
    metadata = json.loads(path.read_text())
    original = AgentRuntimeClient.call

    def after_first_record(self, operation, body=None, **kwargs):
        reply = original(self, operation, body, **kwargs)
        if operation == "dag" and body.get("operation") == "record" and body["request"]["node_id"] == "a":
            changed = (json.loads((other.directory / "agent_runtime.json").read_text()) if replacement == "service"
                       else {**metadata, replacement: "replacement-fixture-value"})
            path.write_text(json.dumps(changed))
        return reply

    try:
        other.start()
        batch = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
        monkeypatch.setattr(AgentRuntimeClient, "call", after_first_record)
        result = run_dag(graph(), batch_id=batch["batch_id"])
        assert not result.succeeded and target.count == 1 and other_target.count == 0
        assert other.runtime.list() == []
        saved = source.runtime.batches.control("get", {"batch_id": batch["batch_id"]})
        assert [row["phase"] for row in saved["nodes"]] == ["confirmed", "pending"]
        with pytest.raises(AgentTaskError, match="already started"):
            source.runtime.batches.control("begin", {"batch_id": batch["batch_id"],
                "definition": graph(), "max_parallel": 4})
    finally:
        path.write_text(json.dumps(metadata))
        other.close()


def test_admin_inspection_uses_original_owners_keys_on_the_owning_runtime(service, monkeypatch, tmp_path):
    client, source, target = service
    other = AgentRuntimeService(tmp_path / "other", targets={"fixture": Target()})
    try:
        other.start()
        with authorization_scope(AuthorizationContext("owner", "operator")):
            batch = client.call("dag", {"operation": "register", "request": {"definition": graph()}})
        with authorization_scope(AuthorizationContext("reviewer", "admin")):
            client.call("dag", {"operation": "run_background", "request": {
                "batch_id": batch["batch_id"], "definition": graph(), "max_parallel": 4}})
            until(lambda: source.runtime.batches.control("get", {
                "batch_id": batch["batch_id"]})["state"] == "succeeded")
            monkeypatch.setattr("je_auto_control.utils.agent_runtime.client.default_connection_path",
                                lambda: other.directory / "agent_runtime.json")
            result = client.call("dag", {"operation": "inspect", "request": {"batch_id": batch["batch_id"]}})
        assert target.count == 2 and other.runtime.list() == []
        assert all(node["recorded_completion"] is True for node in result["nodes"])
        assert all(node["request_match"] == "matches" for node in result["nodes"])
    finally:
        other.close()
