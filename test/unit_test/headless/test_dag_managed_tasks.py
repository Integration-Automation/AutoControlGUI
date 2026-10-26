"""Managed DAG nodes use closed APIs, preserve uncertainty and never infer completion."""
import copy
import threading
from concurrent.futures import CancelledError

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.dag import DagDefinitionError, parse_dag, run_dag
from je_auto_control.utils.dag import managed_tasks
from je_auto_control.utils.exception.cancellation import (
    CancellationToken, cancellation_scope, current_cancellation_token,
)
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


def task(**changes):
    spec = {"goal": "fixture", "target": "fixture", "mode": "skill", "allowed_tools": ["AC_increment"],
            "actions": [{"tool": "AC_increment"}],
            "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}]}
    return {"spec": spec, "idempotency_key": "reviewed-one", "wait_seconds": 2, **changes}


def test_versioned_dag_exports_match_historical_facade():
    import je_auto_control
    from je_auto_control import api
    from je_auto_control.api import core

    for name in ("DagDefinition", "DagDefinitionError", "DagNode", "DagRunResult", "NodeResult",
                 "parse_dag", "run_dag"):
        assert getattr(je_auto_control, name) is getattr(core, name) is getattr(api, name)
        assert name in core.__all__ and name in api.__all__


def definition(payload=None, host="local"):
    return {"nodes": [{"id": "one", "host": host, "task": payload or task()},
                      {"id": "two", "actions": [], "depends_on": ["one"]}]}


def completed(**changes):
    return {"task_id": "task-one", "state": "succeeded", "metadata": {
        "input_released": True, "completion_contract": 1, "history_path": "private-remote-path"},
        "verification": [{"kind": "result_equals", "status": "passed"}], **changes}


class Endpoint:
    def __init__(self, status=None):
        self.status = status or completed()
        self.calls = []

    def __call__(self, operation, body, timeout):
        self.calls.append((operation, copy.deepcopy(body), timeout))
        if operation == "submit":
            return {"task_id": "task-one", "state": "queued"}
        if operation == "pause":
            return {"task_id": "task-one", "state": "paused", "metadata": {"input_released": True}}
        return self.status


def test_task_payload_is_detached_frozen_and_does_not_resolve_destination_roots():
    payload = task()
    payload["spec"]["roots"] = ["/remote-only/artifacts"]
    node = parse_dag(definition(payload)).nodes[0]
    payload["spec"]["goal"] = "changed"
    assert node.task["spec"]["goal"] == "fixture"
    assert node.task["spec"]["roots"] == ("/remote-only/artifacts",)
    with pytest.raises(TypeError):
        node.task["spec"]["goal"] = "changed"


@pytest.mark.parametrize("change", [
    {"idempotency_key": ""}, {"idempotency_key": "x" * 257}, {"wait_seconds": True},
    {"wait_seconds": 0}, {"wait_seconds": float("inf")}, {"wait_seconds": 86_401}, {"url": "http://evil"},
])
def test_malformed_envelope_is_refused_before_dispatch(change):
    with pytest.raises(DagDefinitionError):
        parse_dag(definition(task(**change)))


def test_external_or_ambiguous_payloads_are_refused():
    payload = task()
    payload["spec"]["mode"] = "external"
    with pytest.raises(DagDefinitionError):
        parse_dag(definition(payload))
    graph = definition()
    graph["nodes"][0]["actions"] = []
    with pytest.raises(DagDefinitionError):
        parse_dag(graph)


def test_verified_completion_advances_dependencies_without_copying_private_metadata(monkeypatch):
    from je_auto_control.utils.executor.action_executor import executor

    endpoint = Endpoint()
    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: endpoint)
    monkeypatch.setitem(executor.event_dict, "AC_dag_verified_child", lambda: True)
    graph = definition()
    graph["nodes"][1]["actions"] = [["AC_dag_verified_child"]]
    result = run_dag(graph)
    assert result.succeeded
    assert [row[0] for row in endpoint.calls] == ["submit", "get"]
    assert endpoint.calls[0][1]["idempotency_key"] == "reviewed-one"
    assert result.nodes["one"].result["outcome"] == "completed"
    assert "private-remote-path" not in str(result.to_dict())


@pytest.mark.parametrize("status", [
    completed(metadata={"input_released": True}),
    completed(metadata={"input_released": True, "completion_contract": True}),
    completed(metadata={"input_released": 1, "completion_contract": 1}),
    completed(metadata={"input_released": False, "completion_contract": 1}),
    completed(verification=[]), completed(verification=[{"kind": "screen", "status": "passed"}]),
    completed(verification=[{"kind": "result_equals", "status": "unknown"}]),
    completed(task_id="other-task"), completed(state="waiting_user"), completed(state="recovering"),
    completed(state="failed"), completed(state="cancelled"), completed(state="timed_out"),
])
def test_unverified_or_stopped_task_blocks_downstream(status, monkeypatch):
    endpoint = Endpoint(status)
    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: endpoint)
    result = run_dag(definition())
    assert not result.succeeded
    assert result.nodes["one"].result["outcome"] == "requires_review"
    assert result.nodes["two"].status == "skipped"
    assert [row[0] for row in endpoint.calls] == ["submit", "get", "pause"]


def test_lost_submit_reply_keeps_key_and_never_retries_or_resumes(monkeypatch):
    calls = []

    def endpoint(operation, _body, _timeout):
        calls.append(operation)
        raise AgentTaskError("diagnostic-with-private-token")

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: endpoint)
    result = run_dag(definition())
    assert calls == ["submit"]
    assert result.nodes["one"].result == {"outcome": "unknown", "task_id": None,
        "idempotency_key": "reviewed-one", "task_state": "unknown", "input_released": None}
    assert "private-token" not in str(result.to_dict())


@pytest.mark.parametrize("reason", ["stop", "cancel", "timeout"])
def test_interrupted_wait_requests_pause_with_cancellation_suspended(reason, monkeypatch):
    token = CancellationToken(1)
    stop = threading.Event()
    calls = []

    def endpoint(operation, _body, _timeout):
        calls.append(operation)
        if operation == "submit":
            return {"task_id": "task-one"}
        if operation == "get":
            if reason == "stop":
                stop.set()
            elif reason == "cancel":
                token.cancel()
            return {"task_id": "task-one", "state": "running"}
        assert current_cancellation_token() is None
        raise AgentTaskError("pause acknowledgement lost")

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: endpoint)
    with cancellation_scope(token):
        if reason == "cancel":
            with pytest.raises(CancelledError):
                run_dag(definition(), stop_event=stop)
        else:
            payload = task(wait_seconds=0.01) if reason == "timeout" else task()
            result = run_dag(definition(payload), stop_event=stop)
            assert not result.succeeded
            assert result.nodes["one"].result["input_released"] is None
    assert calls == ["submit", "get", "pause"]


def test_owner_revocation_during_poll_stops_dispatch_and_preserves_review(tmp_path, monkeypatch):
    store = UserStore(tmp_path / "users.json")
    store.add_user(user_id="caller", display_name="Caller", role="operator")
    calls = []

    def endpoint(operation, _body, _timeout):
        calls.append(operation)
        if operation == "get":
            store.remove_user("caller")
        return {"task_id": "task-one", "state": "running"}

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: endpoint)
    with authorization_scope(AuthorizationContext("caller", "operator", store_path=str(store.path))):
        result = run_dag(definition())
    assert not result.succeeded
    assert calls == ["submit", "get", "pause"]


def test_remote_operator_is_refused_before_connection(monkeypatch):
    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: pytest.fail("opened host credentials"))
    with authorization_scope(AuthorizationContext("caller", "operator")):
        assert not run_dag(definition(host="remote")).succeeded


def test_legacy_action_node_without_task_field_still_uses_local_executor():
    from types import SimpleNamespace
    from je_auto_control.utils.dag.runner import _default_local_runner

    calls = []
    node = SimpleNamespace(host="local", actions=[["AC_fixture", {}]], action_file=None, id="legacy")
    executor = SimpleNamespace(execute_action=lambda actions, **kwargs: calls.append((actions, kwargs)) or "done")
    assert _default_local_runner(node, None, executor) == "done"
    assert calls == [([["AC_fixture", {}]], {"raise_on_error": True})]


def test_nested_task_cannot_dispatch_another_managed_task(monkeypatch):
    from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
    from je_auto_control.utils.agent_runtime.models import AgentTaskSpec

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: pytest.fail("recursive submission"))
    operation = TaskOperation(AgentTaskSpec.from_dict(task()["spec"]), lambda: None, None)
    with operation_scope(operation):
        result = run_dag(definition())
    assert not result.succeeded
    assert "recursively" in result.nodes["one"].error


def test_remote_task_cannot_serialize_local_origin_witnesses(monkeypatch):
    payload = task()
    payload["spec"]["options"] = {"origin_policies": ["local-private-witness"]}
    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: pytest.fail("forwarded local witness"))
    result = run_dag(definition(payload, host="remote"))
    assert not result.succeeded
    assert "origin witnesses" in result.nodes["one"].error


def test_remote_connection_uses_only_closed_routes_and_registered_token(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from je_auto_control.utils.admin import admin_client
    from je_auto_control.utils.agent_runtime import transport

    host = SimpleNamespace(label="remote", base_url="https://fixture.invalid/base", token="fixture-host-token")
    console = admin_client.AdminConsoleClient(persist_path=tmp_path / 'hosts.json')
    console.add_host(host.label, host.base_url, host.token)
    monkeypatch.setattr(admin_client, "_default_console", console)
    calls = []

    def request(url, **kwargs):
        assert "delegate_local" not in kwargs
        assert kwargs["token"] == host.token
        calls.append((url, kwargs))
        return {}

    monkeypatch.setattr(transport, "request_json", request)
    connection = managed_tasks._connection("remote")
    connection("submit", {"spec": {}}, 3)
    connection("get", {"task_id": "one"}, 2)
    connection("pause", {"task_id": "one"}, 1)
    with pytest.raises(AgentTaskError):
        connection("resume", {}, 3)
    assert [row[0] for row in calls] == ["https://fixture.invalid/base/agent/submit",
        "https://fixture.invalid/base/agent/task?task_id=one", "https://fixture.invalid/base/agent/pause"]
    assert calls[-1][1]["control"] is True


@pytest.mark.parametrize("url", ["file:///private", "https://user:pass@fixture.invalid", "http://fixture.invalid:0",
                              "https://fixture.invalid/?token=bad", "https://fixture.invalid/#bad"])
def test_invalid_registered_endpoint_is_refused(url, tmp_path, monkeypatch):
    import json
    from je_auto_control.utils.admin import admin_client

    console = admin_client.AdminConsoleClient(persist_path=tmp_path / 'hosts.json')
    console.persist_path.write_text(json.dumps({'hosts': [
        {'label': 'remote', 'base_url': url, 'token': 'fixture-host-token'}]}), encoding='utf-8')
    monkeypatch.setattr(admin_client, "_default_console", console)
    with pytest.raises(AgentTaskError):
        managed_tasks._connection("remote")
