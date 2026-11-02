"""DAG workers retain caller restrictions and refresh authority before dispatch."""
from concurrent.futures import CancelledError

import pytest

from je_auto_control.utils.dag.runner import run_dag
from je_auto_control.utils.exception.cancellation import (
    CancellationToken, cancellation_checkpoint, cancellation_scope,
)
from je_auto_control.utils.executor.dispatch import command_guard, dispatch_checkpoint
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, authorization_scope, current_authorization,
)
from je_auto_control.utils.rbac.users import UserStore


def definition(host="local"):
    return {"nodes": [{"id": "one", "host": host, "actions": []}]}


@pytest.mark.parametrize("host", ["local", "other-host"])
def test_custom_workers_retain_identity_and_intersected_command_guards(host):
    owner = AuthorizationContext("caller", "operator")
    seen = []

    def deny(_name, _arguments):
        raise PermissionError("parent command ceiling")

    def runner(*_args):
        seen.append(current_authorization())
        dispatch_checkpoint("AC_fixture", {})

    with authorization_scope(owner), command_guard(deny):
        result = run_dag(definition(host), local_runner=runner, remote_runner=runner)
    assert seen == [owner]
    assert not result.succeeded
    assert "parent command ceiling" in result.nodes["one"].error
    assert current_authorization() is None


def test_custom_worker_retains_cancellation():
    token = CancellationToken(1)

    def runner(*_args):
        token.cancel()
        cancellation_checkpoint()

    with cancellation_scope(token), pytest.raises(CancelledError):
        run_dag(definition(), local_runner=runner)


@pytest.mark.parametrize("change", ["remove", "demote"])
def test_each_node_refreshes_store_owner_before_runner(tmp_path, change):
    store = UserStore(tmp_path / "users.json")
    store.add_user(user_id="caller", display_name="Caller", role="operator")
    owner = AuthorizationContext("caller", "operator", store_path=str(store.path))
    seen = []

    def runner(node, _definition):
        seen.append((node.id, current_authorization().role))
        if change == "remove":
            store.remove_user("caller")
        else:
            store.set_role("caller", "viewer")

    graph = {"nodes": [
        {"id": "one", "actions": []},
        {"id": "two", "actions": [], "depends_on": ["one"]},
    ]}
    with authorization_scope(owner):
        result = run_dag(graph, local_runner=runner)
    if change == "remove":
        assert not result.succeeded
        assert seen == [("one", "operator")]
        assert "no longer authorised" in result.nodes["two"].error
    else:
        assert result.succeeded
        assert seen == [("one", "operator"), ("two", "viewer")]


@pytest.mark.parametrize("role", ["operator", "viewer"])
def test_default_remote_dispatch_refuses_host_credentials_before_address_book(role, monkeypatch):
    from je_auto_control.utils.admin import admin_client

    def forbidden():
        pytest.fail("unauthorised dispatch opened the host address book")

    monkeypatch.setattr(admin_client, "default_admin_console", forbidden)
    with authorization_scope(AuthorizationContext("caller", role)):
        result = run_dag(definition("other-host"))
    assert not result.succeeded
    assert "manage_hosts" in result.nodes["one"].error


@pytest.mark.parametrize("role", ["admin", None])
def test_default_remote_dispatch_keeps_admin_and_trusted_python_support(role, monkeypatch):
    from je_auto_control.utils.admin import admin_client

    class Console:
        def broadcast_execute(self, actions, *, labels, raise_on_error):
            assert actions == [] and labels == ["other-host"] and raise_on_error
            return [{"ok": True, "result": {"verified": True}}]

    monkeypatch.setattr(admin_client, "default_admin_console", Console)
    owner = AuthorizationContext("caller", role) if role else None
    with authorization_scope(owner):
        result = run_dag(definition("other-host"))
    assert result.succeeded
    assert result.nodes["one"].result == {"verified": True}


def test_default_local_executor_cannot_borrow_trusted_worker_authority(monkeypatch):
    from je_auto_control.utils.executor.action_executor import executor

    called = []
    monkeypatch.setitem(executor.event_dict, "AC_admin_list_hosts", lambda: called.append(True))
    graph = {"nodes": [{"id": "one", "actions": [["AC_admin_list_hosts"]]}]}
    with authorization_scope(AuthorizationContext("caller", "operator")):
        result = run_dag(graph)
    assert not result.succeeded
    assert called == []
    assert "manage_hosts" in result.nodes["one"].error


def test_remote_node_refreshes_admin_demotion_before_opening_host_book(tmp_path, monkeypatch):
    from je_auto_control.utils.admin import admin_client

    store = UserStore(tmp_path / "users.json")
    store.add_user(user_id="caller", display_name="Caller", role="admin")

    def forbidden():
        pytest.fail("demoted owner opened remote credentials")

    monkeypatch.setattr(admin_client, "default_admin_console", forbidden)
    graph = {"nodes": [
        {"id": "one", "actions": []},
        {"id": "two", "host": "other-host", "actions": [], "depends_on": ["one"]},
    ]}
    owner = AuthorizationContext("caller", "admin", store_path=str(store.path))
    with authorization_scope(owner):
        result = run_dag(graph, local_runner=lambda *_args: store.set_role("caller", "operator"))
    assert result.nodes["one"].status == "succeeded"
    assert result.nodes["two"].status == "failed"
    assert "manage_hosts" in result.nodes["two"].error
