"""Reauthorization reaches authenticated transport and CLI without replacing source policy files."""
from unittest.mock import Mock

import pytest

from je_auto_control.cli import build_parser
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.origin_policy import origin_scope
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from .test_agent_origin_policy import origin_directory as origin_directory
from .test_agent_runtime_service import service as service


def test_cli_exposes_distinct_review_and_approval_operations_without_startup():
    parser = build_parser()
    for operation in ("review_authorization", "create_authorized"):
        parsed = parser.parse_args(["agent-task", "recovery", operation, "review.json"])
        assert parsed.recovery_operation == operation and parsed.request == "review.json"


def test_authenticated_http_reapproval_keeps_owner_and_scope_bound(service, tmp_path, monkeypatch):
    client, instance = service
    allowed = tmp_path / "data"
    allowed.mkdir()
    narrow = allowed / "reports"
    narrow.mkdir()
    old, current = PathPolicy([allowed]), PathPolicy([narrow])
    old_id, current_id = old.managed_origin(), current.managed_origin()
    start = Mock()
    monkeypatch.setattr(instance.runtime.background, "start", start)
    with authorization_scope(AuthorizationContext("alice", "operator")), origin_scope(old_id):
        source = instance.runtime.submit({"goal": "read two values", "target": "counter", "mode": "skill",
            "roots": [str(allowed)], "allowed_tools": ["AC_increment"],
            "actions": [{"tool": "AC_increment"}, {"tool": "AC_increment"}],
            "success_criteria": [{"kind": "result_equals", "key": "value", "value": 2}]})
        frame = client.call("observe", {"task_id": source.task_id})
        client.call("act", {"task_id": source.task_id, "action": {"tool": "AC_increment",
                                                                "observation_id": frame["observation_id"]}})
        client.call("pause", {"task_id": source.task_id})
    old.revoke_managed_origin()
    with authorization_scope(AuthorizationContext("alice", "operator")), origin_scope(current_id):
        view = client.call("recovery", {"operation": "review_authorization", "request": {"task_id": source.task_id}})
        start.assert_not_called()
        assert view["draft"]["roots"] == [str(narrow.resolve())]
        request = {"task_id": source.task_id, "snapshot": view["snapshot"], "spec": view["draft"],
                   "authorization_review": view["authorization_review"], "note": "Reapproved the report root"}
        child = client.call("recovery", {"operation": "create_authorized", "request": request})["task_id"]
        start.assert_called_once_with(child)
        result = client.call("get", {"task_id": child})
        assert result["metadata"]["recovery"]["reauthorization"]["actor"] == "alice"
        frame = client.call("observe", {"task_id": child})
        client.call("act", {"task_id": child, "action": {"tool": "AC_increment",
                                                        "observation_id": frame["observation_id"]}})
        assert client.call("finish", {"task_id": child})["state"] == "succeeded"
    with authorization_scope(AuthorizationContext("bob", "operator")), origin_scope(current_id):
        with pytest.raises(AgentTaskError):
            client.call("recovery", {"operation": "review_authorization", "request": {"task_id": source.task_id}})
    assert instance.runtime.get(source.task_id).state == "paused"
    assert len(instance.runtime.store.actions(source.task_id)) == 1
