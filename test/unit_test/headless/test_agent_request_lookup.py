"""Lost submission replies can be inspected without repeating any effects."""
from unittest.mock import patch

import pytest

from headless.test_agent_runtime import FakeTarget, specification
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, AuthorizationError, authorization_scope,
)
from je_auto_control.utils.rbac.users import UserStore


def test_lookup_miss_then_late_acceptance_does_not_create_or_dispatch_work(tmp_path):
    target = FakeTarget()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": target})
    try:
        assert runtime.lookup("late-key") == {"found": False, "task": None, "spec_match_contract": 1}
        assert runtime.list() == []
        task = runtime.submit(specification(), idempotency_key="late-key")
        result = runtime.lookup("late-key")
        assert result["found"] is True and result["task"]["task_id"] == task.task_id
        assert result["task"]["state"] == "queued"
        assert target.calls == [] and not runtime._leases
        assert runtime.store.actions(task.task_id) == []
    finally:
        runtime.close()


def test_key_namespace_includes_principal_store_and_never_searches_other_owners(tmp_path):
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        with authorization_scope(AuthorizationContext("alice", "operator")):
            alice = runtime.submit(specification(), idempotency_key="same-key")
        with authorization_scope(AuthorizationContext("bob", "operator")):
            assert runtime.lookup("same-key")["found"] is False
            bob = runtime.submit(specification(), idempotency_key="same-key")
            assert runtime.lookup("same-key")["task"]["task_id"] == bob.task_id
        with authorization_scope(AuthorizationContext("alice", "admin")):
            assert runtime.lookup("same-key")["task"]["task_id"] == alice.task_id
        # A trusted host can inspect explicit IDs, but a bare key never means all owners.
        assert runtime.lookup("same-key")["found"] is False
        first = UserStore(tmp_path / "first.json")
        second = UserStore(tmp_path / "second.json")
        for store in (first, second):
            store.add_user(user_id="alice", display_name="Alice", role="operator")
        with authorization_scope(AuthorizationContext("alice", "operator", store_path=str(first.path))):
            runtime.submit(specification(), idempotency_key="store-key")
        with authorization_scope(AuthorizationContext("alice", "operator", store_path=str(second.path))):
            assert runtime.lookup("store-key")["found"] is False
    finally:
        runtime.close()


def test_revoked_owner_and_viewer_cannot_probe_request_acceptance(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.add_user(user_id="alice", display_name="Alice", role="operator")
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        identity = AuthorizationContext("alice", "operator", store_path=str(store.path))
        with authorization_scope(identity):
            runtime.submit(specification(), idempotency_key="key")
            store.remove_user("alice")
            with pytest.raises(AuthorizationError):
                runtime.lookup("key")
        with authorization_scope(AuthorizationContext("reader", "viewer")), pytest.raises(AuthorizationError):
            runtime.lookup("key")
    finally:
        runtime.close()


@pytest.mark.parametrize("key", [None, False, 1, [], "", "x" * 257, "\ud800"])
def test_invalid_keys_fail_before_lookup(tmp_path, key):
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        with pytest.raises(AgentTaskError):
            runtime.lookup(key)
        assert runtime.list() == []
    finally:
        runtime.close()


def test_accepted_key_survives_service_restart_without_resume(tmp_path):
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    task = runtime.submit(specification(), idempotency_key="stable-key")
    runtime.close()
    replacement = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        found = replacement.lookup("stable-key")
        assert found["task"]["task_id"] == task.task_id and found["task"]["state"] == "queued"
        assert not replacement._leases
    finally:
        replacement.close()


def test_real_http_lost_submit_reply_is_recovered_by_lookup_without_resubmission(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import client as client_module

    target = FakeTarget()
    service = AgentRuntimeService(tmp_path, targets={"fixture": target})
    service.start()
    client = AgentRuntimeClient(tmp_path / "agent_runtime.json")
    real = client_module.request_json
    calls = []

    def lose_submit(url, **kwargs):
        calls.append(url.rsplit("/", 1)[-1])
        result = real(url, **kwargs)
        if url.endswith("/submit"):
            raise AgentTaskError("fixture lost accepted reply")
        return result

    monkeypatch.setattr(client_module, "request_json", lose_submit)
    try:
        with authorization_scope(AuthorizationContext("alice", "operator")):
            with pytest.raises(AgentTaskError, match="lost accepted reply"):
                client.call("submit", {"spec": specification().to_dict(), "idempotency_key": "lost-reply"})
            result = client.call("lookup", {"idempotency_key": "lost-reply"})
        assert result["found"] is True and result["task"]["state"] == "queued"
        assert calls == ["submit", "lookup"]
        assert len(service.runtime.list()) == 1 and not service.runtime._leases
        assert target.calls == []
        with authorization_scope(AuthorizationContext("bob", "operator")):
            assert client.call("lookup", {"idempotency_key": "lost-reply"})["found"] is False
        with authorization_scope(AuthorizationContext("reader", "viewer")), pytest.raises(AgentTaskError):
            client.call("lookup", {"idempotency_key": "lost-reply"})
        with pytest.raises(AgentTaskError):
            client.call("lookup", {"idempotency_key": "lost-reply", "submit": True})
    finally:
        service.close()


def test_public_command_mcp_and_api_share_read_only_lookup_contract():
    import je_auto_control as ac
    from je_auto_control import api
    from je_auto_control.api import core
    from je_auto_control.utils.agent_runtime import api as task_api
    from je_auto_control.utils.agent_runtime.commands import CATALOG
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.utils.rbac.policy import capability_for_tool

    assert ac.lookup_agent_task is api.lookup_agent_task is core.lookup_agent_task is task_api.lookup_agent_task
    entry = CATALOG["AC_agent_task_lookup"]
    assert entry[0] is ac.lookup_agent_task and entry[3] is True
    registry = build_default_tool_registry()
    tool = next((tool for tool in registry if tool.name == "ac_agent_task_lookup"), None)
    assert tool is not None
    assert capability_for_tool("ac_agent_task_lookup", True) == "drive_input"
    with patch.object(task_api, "AgentRuntimeClient") as client:
        client.return_value.call.return_value = {"found": False, "task": None}
        assert ac.lookup_agent_task("key")["found"] is False
        client.return_value.call.assert_called_once_with("lookup", {"idempotency_key": "key"})


def test_cli_lookup_does_not_choose_submit_or_resume(monkeypatch):
    import argparse
    from je_auto_control.utils.agent_runtime import api, cli

    parser = argparse.ArgumentParser()
    cli.register_parser(parser.add_subparsers(), lambda *_args: 0)
    arguments = parser.parse_args(["agent-task", "lookup", "original-key"])
    seen = []
    monkeypatch.setattr(api, "lookup_agent_task", lambda key: seen.append(key) or {"found": False, "task": None})
    assert cli.run(arguments) == {"found": False, "task": None}
    assert seen == ["original-key"]
