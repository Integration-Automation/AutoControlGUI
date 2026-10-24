"""DAG recovery inspection never creates, resumes or certifies a replacement task."""
import json
import threading
from concurrent.futures import CancelledError

import pytest

from headless.test_dag_managed_tasks import completed, definition, task
from headless.test_agent_runtime import FakeTarget, specification
from je_auto_control.utils.agent_runtime import AgentTaskError, inspect_agent_dag
from je_auto_control.utils.dag import DagDefinitionError, managed_tasks
from je_auto_control.utils.exception.cancellation import CancellationToken, cancellation_scope
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


def test_inspection_uses_lookup_only_and_never_grants_matching_or_resume(monkeypatch):
    calls = []

    def connection(_host):
        def call(operation, body, timeout):
            calls.append((operation, body, timeout))
            return {"found": True, "task": completed()}
        return call

    monkeypatch.setattr(managed_tasks, "_connection", connection)
    result = inspect_agent_dag(definition())
    assert result["inspection_only"] is True and result["resume_permitted"] is False
    first, second = result["nodes"]
    assert first["task_id"] == "task-one" and first["lookup"] == "found"
    assert first["recorded_completion"] is True and first["request_match"] == "unverified"
    assert second["lookup"] == "not_managed"
    assert "private-remote-path" not in str(result)
    assert len(calls) == 1 and calls[0][0:2] == ("lookup", {"idempotency_key": "reviewed-one"})
    assert 0 < calls[0][2] <= 5


@pytest.mark.parametrize("reply,expected", [
    ({"found": False, "task": None}, "not_found"),
    ({"found": True, "task": None}, "unavailable"),
    ({"found": False, "task": completed()}, "unavailable"),
    ({"found": 1, "task": completed()}, "unavailable"),
    ({"found": True, "task": completed(task_id="../private")}, "unavailable"),
    ({"found": True, "task": completed(state=[])}, "unavailable"),
])
def test_missing_or_malformed_status_never_becomes_completion(reply, expected, monkeypatch):
    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: lambda *_args: reply)
    result = inspect_agent_dag(definition())
    assert result["nodes"][0]["lookup"] == expected
    assert result["resume_permitted"] is False


def test_remote_failures_are_bounded_fixed_diagnostics(monkeypatch):
    def fail(*_args):
        raise AgentTaskError("remote-token-and-private-store-path")

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: fail)
    result = inspect_agent_dag(definition())
    assert result["nodes"][0]["error"] == "lookup_unavailable"
    assert "remote-token" not in str(result)


@pytest.mark.parametrize("role,host", [("viewer", "local"), ("operator", "remote")])
def test_role_failure_prevents_opening_a_connection(role, host, monkeypatch):
    monkeypatch.setattr(managed_tasks, "_connection", lambda *_args: pytest.fail("opened forbidden connection"))
    with authorization_scope(AuthorizationContext("caller", role)), pytest.raises(AuthorizationError):
        inspect_agent_dag(definition(host=host))


def test_owner_revocation_during_lookup_discards_the_reply(tmp_path, monkeypatch):
    store = UserStore(tmp_path / "users.json")
    store.add_user(user_id="caller", display_name="Caller", role="operator")

    def lookup(*_args):
        store.remove_user("caller")
        return {"found": True, "task": completed()}

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: lookup)
    owner = AuthorizationContext("caller", "operator", store_path=str(store.path))
    with authorization_scope(owner), pytest.raises(AuthorizationError):
        inspect_agent_dag(definition())


def test_cancellation_and_explicit_stop_do_not_send_control_requests(monkeypatch):
    token = CancellationToken(1)
    calls = []

    def lookup(operation, *_args):
        calls.append(operation)
        token.cancel()
        return {"found": True, "task": completed()}

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: lookup)
    with cancellation_scope(token), pytest.raises(CancelledError):
        inspect_agent_dag(definition())
    assert calls == ["lookup"]
    stop = threading.Event()
    stop.set()
    with managed_tasks.managed_stop_scope(stop), pytest.raises(AgentTaskError, match="stopped"):
        inspect_agent_dag(definition())
    assert calls == ["lookup"]


@pytest.mark.parametrize("timeout", [False, 0, 301, float("inf")])
def test_invalid_budgets_fail_before_queries(timeout, monkeypatch):
    monkeypatch.setattr(managed_tasks, "_connection", lambda *_args: pytest.fail("invalid budget made a request"))
    with pytest.raises(AgentTaskError):
        inspect_agent_dag(definition(), timeout)


def test_graph_bounds_and_cycles_are_checked_before_queries(monkeypatch):
    monkeypatch.setattr(managed_tasks, "_connection", lambda *_args: pytest.fail("invalid graph made a request"))
    graph = {"nodes": [{"id": str(index), "task": task(idempotency_key=str(index))} for index in range(101)]}
    with pytest.raises(DagDefinitionError, match="100 nodes"):
        inspect_agent_dag(graph)
    graph = definition()
    graph["nodes"][0]["depends_on"] = ["two"]
    with pytest.raises(DagDefinitionError, match="cycle"):
        inspect_agent_dag(graph)


@pytest.mark.parametrize("count", [1, 2])
def test_total_deadline_discards_late_reply_and_prevents_another_host_query(monkeypatch, count):
    from types import SimpleNamespace
    from je_auto_control.utils.dag import inspection

    now = [100.0]
    monkeypatch.setattr(inspection, "time", SimpleNamespace(monotonic=lambda: now[0], time=lambda: now[0]))
    calls = []

    def lookup(operation, _body, timeout):
        calls.append((operation, timeout))
        now[0] += 2
        return {"found": False, "task": None}

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: lookup)
    graph = {"nodes": [{"id": str(index), "task": task(idempotency_key=str(index))} for index in range(count)]}
    with pytest.raises(AgentTaskError, match="deadline"):
        inspect_agent_dag(graph, 1)
    assert calls == [("lookup", 1)]


def test_stop_during_last_lookup_discards_reply(monkeypatch):
    stop = threading.Event()

    def lookup(*_args):
        stop.set()
        return {"found": True, "task": completed()}

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: lookup)
    graph = {"nodes": [{"id": "one", "task": task()}]}
    with managed_tasks.managed_stop_scope(stop), pytest.raises(AgentTaskError, match="stopped"):
        inspect_agent_dag(graph)


def test_managed_task_cannot_inspect_other_task_keys(monkeypatch):
    from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
    from je_auto_control.utils.agent_runtime.models import AgentTaskSpec

    monkeypatch.setattr(managed_tasks, "_connection", lambda *_args: pytest.fail("nested lookup"))
    parent = TaskOperation(AgentTaskSpec.from_dict(task()["spec"]), lambda: None, None)
    with operation_scope(parent), pytest.raises(AgentTaskError, match="cannot inspect"):
        inspect_agent_dag(definition())


def test_real_registered_host_lookup_does_not_submit_even_when_reviewed_spec_differs(tmp_path, monkeypatch):
    from je_auto_control.utils.admin import admin_client
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient
    from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
    from je_auto_control.utils.agent_runtime import transport

    target = FakeTarget()
    service = AgentRuntimeService(tmp_path / "service", targets={"fixture": target})
    service.start()
    try:
        accepted = service.runtime.submit(specification(), idempotency_key="reviewed-one")
        frame = service.runtime.observe(accepted.task_id)
        service.runtime.act(accepted.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
        assert service.runtime.finish(accepted.task_id).state == "succeeded"
        metadata = json.loads((service.directory / "agent_runtime.json").read_text())
        console = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
        console.add_host("remote", metadata["url"], metadata["token"])
        monkeypatch.setattr(admin_client, "default_admin_console", lambda: console)
        real = transport.request_json
        calls = []

        def request(url, **kwargs):
            calls.append((url, kwargs))
            assert "delegate_local" not in kwargs
            return real(url, **kwargs)

        monkeypatch.setattr(transport, "request_json", request)
        graph = definition(host="remote")
        graph["nodes"][0]["task"]["spec"]["goal"] = "different reviewed task"
        with authorization_scope(AuthorizationContext("local-admin", "admin")):
            result = inspect_agent_dag(graph)
        first = result["nodes"][0]
        assert first["task_id"] == accepted.task_id and first["recorded_completion"] is True
        assert first["request_match"] == "unverified" and result["resume_permitted"] is False
        assert len(calls) == 1 and calls[0][0].endswith("/agent/lookup")
        assert calls[0][1]["body"] == {"idempotency_key": "reviewed-one"}
        assert target.calls == ["AC_increment"] and len(service.runtime.list()) == 1
        assert "history_path" not in str(result)
    finally:
        service.close()


def test_inspection_api_exports_and_cli_keep_the_same_read_only_path(monkeypatch):
    import argparse
    import je_auto_control as ac
    from je_auto_control import api
    from je_auto_control.api import core
    from je_auto_control.utils.agent_runtime import cli

    assert ac.inspect_agent_dag is api.inspect_agent_dag is core.inspect_agent_dag
    parser = argparse.ArgumentParser()
    cli.register_parser(parser.add_subparsers(), lambda *_args: 0)
    arguments = parser.parse_args(["agent-task", "inspect-dag", "reviewed.json", "--timeout-seconds", "4"])
    graph = definition()
    seen = []
    monkeypatch.setattr(cli, "_read", lambda _path: graph)
    monkeypatch.setattr(cli.api, "inspect_agent_dag", lambda *args: seen.append(args) or {"inspection_only": True})
    assert cli.run(arguments) == {"inspection_only": True}
    assert seen == [(graph, 4)]
