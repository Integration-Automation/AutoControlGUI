"""Reviewed recovery reaches public facades, CLI and authenticated HTTP without real applications."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime import api, AgentTaskError
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from .test_agent_runtime_service import service as service


def test_public_facades_and_cli_forward_the_same_review_request(tmp_path, monkeypatch):
    import je_auto_control as ac
    from je_auto_control.api import core
    from je_auto_control.cli import build_parser
    from je_auto_control.utils.agent_runtime.cli import run
    call = Mock(return_value={"approval_required": True})
    monkeypatch.setattr(api, "AgentRuntimeClient", lambda: SimpleNamespace(call=call))
    assert ac.manage_agent_recovery is core.manage_agent_recovery is api.manage_agent_recovery
    request = {"task_id": "stopped-task"}
    ac.manage_agent_recovery("preview", request)
    call.assert_called_once_with("recovery", {"operation": "preview", "request": request})
    path = tmp_path / "review.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    arguments = build_parser().parse_args(["agent-task", "recovery", "preview", str(path)])
    assert run(arguments) == {"approval_required": True}
    assert call.call_count == 2
    with pytest.raises(SystemExit):
        build_parser().parse_args(["agent-task", "recovery", "preview"])


def test_real_service_authenticates_preview_and_deduplicates_explicit_creation(service, monkeypatch):
    client, instance = service
    start = Mock()
    monkeypatch.setattr(instance.runtime.background, "start", start)
    with authorization_scope(AuthorizationContext("alice", "operator")):
        source = instance.runtime.submit({"goal": "review and count", "target": "counter", "mode": "skill",
            "allowed_tools": ["AC_increment"], "actions": [{"tool": "AC_increment"}],
            "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}]})
        instance.runtime.pause(source.task_id)
        view = client.call("recovery", {"operation": "preview", "request": {"task_id": source.task_id}})
        start.assert_not_called()
        request = {"task_id": source.task_id, "snapshot": view["snapshot"], "spec": view["draft"],
                   "note": "Reviewed the new counter task"}
        first = client.call("recovery", {"operation": "create", "request": request})
        assert client.call("recovery", {"operation": "create", "request": request})["task_id"] == first["task_id"]
        result = client.call("get", {"task_id": first["task_id"]})
        assert result["metadata"]["recovery"]["source_task"] == source.task_id
    assert len(instance.runtime.list()) == 2
    with authorization_scope(AuthorizationContext("bob", "operator")):
        with pytest.raises(AgentTaskError):
            client.call("recovery", {"operation": "preview", "request": {"task_id": source.task_id}})
    with authorization_scope(AuthorizationContext("alice", "viewer")):
        with pytest.raises(AgentTaskError):
            client.call("recovery", {"operation": "create", "request": request})
    assert instance.runtime.get(source.task_id).state == "paused"
