"""Local principal and live-root witnesses must never be copied to generic authenticated HTTP destinations."""
import json
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime import origin_policy
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transport import request_json
from je_auto_control.utils.agent_runtime.delegation import HEADER as PRINCIPAL_HEADER, verify_principal
from je_auto_control.utils.agent_runtime.origin_policy import HEADER as ORIGIN_HEADER, origin_scope
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    def transport(call):
        recorded.append(call)
        return {"status": 200, "json": {"ok": True}}

    monkeypatch.setattr("je_auto_control.utils.agent_runtime.transport.urllib_transport", transport)
    return recorded


@pytest.mark.parametrize("url", ["https://remote.test/agent/tasks", "http://127.0.0.1:1234/agent/tasks"])
def test_generic_bearer_transport_does_not_export_ambient_local_authority(calls, tmp_path, monkeypatch, url):
    monkeypatch.setattr(origin_policy, "_directory", lambda: tmp_path / "origins")
    policy = PathPolicy([tmp_path])
    identifier = policy.managed_origin()
    identity = AuthorizationContext("fixture-user", "operator", str(tmp_path / "private-users.json"))
    try:
        with authorization_scope(identity), origin_scope(identifier):
            assert request_json(url, token="fixture-token") == {"ok": True}
        assert calls[0]["headers"]["Authorization"] == "Bearer fixture-token"
        assert PRINCIPAL_HEADER not in calls[0]["headers"]
        assert ORIGIN_HEADER not in calls[0]["headers"]
        assert calls[0]["follow_redirects"] is False
    finally:
        policy.revoke_managed_origin()


def test_explicit_local_service_delegation_preserves_principal_and_live_roots(calls, tmp_path, monkeypatch):
    monkeypatch.setattr(origin_policy, "_directory", lambda: tmp_path / "origins")
    policy = PathPolicy([tmp_path])
    identifier = policy.managed_origin()
    try:
        with authorization_scope(AuthorizationContext("fixture-user", "operator")), origin_scope(identifier):
            request_json("http://127.0.0.1:1234/agent/tasks", token="fixture-token", delegate_local=True)
        headers = calls[0]["headers"]
        principal = verify_principal(headers[PRINCIPAL_HEADER], "fixture-token", "/agent/tasks")
        assert principal.user_id == "fixture-user" and principal.role == "operator"
        assert headers[ORIGIN_HEADER] == identifier
    finally:
        policy.revoke_managed_origin()


@pytest.mark.parametrize("url", [
    "https://remote.test/agent/tasks", "http://localhost:1234/agent/tasks", "http://127.0.0.1:1234/api/chat",
    "http://127.0.0.1:1234/agent/tasks#fragment", "http://user@127.0.0.1:1234/agent/tasks",
    "http://@127.0.0.1:1234/agent/tasks", "http://127.0.0.1:0/agent/tasks", "http://127.0.0.1/agent/tasks",
])
def test_delegation_rejects_non_service_destinations_before_network(calls, url):
    with pytest.raises(AgentTaskError, match="local service"):
        request_json(url, token="fixture-token", delegate_local=True)
    assert calls == []


def test_delegation_requires_an_explicit_service_token(calls):
    with pytest.raises(AgentTaskError, match="local service"):
        request_json("http://127.0.0.1:1234/agent/tasks", delegate_local=True)
    assert calls == []


@pytest.mark.parametrize("operation", ["list", "targets", "submit", "pause"])
def test_local_client_explicitly_selects_delegation_for_each_route(tmp_path, monkeypatch, operation):
    metadata = tmp_path / "connection.json"
    metadata.write_text(json.dumps({"url": "http://127.0.0.1:1234", "token": "fixture-token"}), encoding="utf-8")
    request = Mock(return_value={"ok": True})
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.client.request_json", request)
    assert AgentRuntimeClient(metadata).call(operation) == {"ok": True}
    assert request.call_args.kwargs.get("delegate_local") is True
