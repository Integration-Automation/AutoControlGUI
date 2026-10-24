"""DAG inspection accepts matching evidence only from the same destination request."""
import copy
import json

import pytest

from headless.test_dag_managed_tasks import completed, definition
from headless.test_agent_runtime import FakeTarget
from je_auto_control.utils.agent_runtime import inspect_agent_dag
from je_auto_control.utils.dag import managed_tasks
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


def reply(**changes):
    return {"found": True, "task": completed(), "spec_match_contract": 1, **changes}


@pytest.mark.parametrize("match", ["matches", "differs", "unverifiable", True, [], None])
def test_matching_reply_is_closed_and_does_not_grant_continuation(match, monkeypatch):
    calls = []

    def call(operation, body, _timeout):
        calls.append((operation, body))
        return reply(spec_match=match) if "spec" in body else reply()

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: call)
    result = inspect_agent_dag(definition())
    expected = match if isinstance(match, str) else "unverifiable"
    assert result["nodes"][0]["request_match"] == expected
    assert result["resume_permitted"] is False
    assert [item[0] for item in calls] == ["lookup", "lookup"]
    assert set(calls[1][1]) == {"idempotency_key", "spec"}


@pytest.mark.parametrize("reports", [
    [], [{"kind": "screen", "status": "passed"}],
    [{"kind": "result_equals", "status": "passed"}] * 2,
    [{"kind": "result_equals", "status": "unknown"}],
])
def test_matched_spec_requires_exact_independent_criteria_reports(reports, monkeypatch):
    def call(_operation, body, _timeout):
        if "spec" in body:
            return reply(task=completed(verification=reports), spec_match="matches")
        return reply()

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: call)
    result = inspect_agent_dag(definition())
    assert result["nodes"][0]["request_match"] == "matches"
    assert result["nodes"][0]["recorded_completion"] is False
    assert result["resume_permitted"] is False


@pytest.mark.parametrize("version", [None, False, True, "1", 1.0, 2])
def test_older_or_invalid_contract_never_receives_spec(version, monkeypatch):
    calls = []

    def call(operation, body, _timeout):
        calls.append((operation, body))
        return reply(spec_match_contract=version)

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: call)
    result = inspect_agent_dag(definition())
    assert result["nodes"][0]["request_match"] == "unverified"
    assert len(calls) == 1 and set(calls[0][1]) == {"idempotency_key"}


@pytest.mark.parametrize("changed", ["removed", "replaced"])
def test_key_mapping_change_invalidates_old_completion_snapshot(changed, monkeypatch):
    calls = []

    def call(operation, body, _timeout):
        calls.append(operation)
        if "spec" not in body:
            return reply()
        if changed == "removed":
            return reply(found=False, task=None, spec_match="not_found")
        return reply(task=completed(task_id="replacement-task"), spec_match="matches")

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: call)
    result = inspect_agent_dag(definition())
    node = result["nodes"][0]
    assert node["lookup"] == "unavailable" and node["request_match"] == "unverifiable"
    assert node["recorded_completion"] is None and node["input_released"] is None
    assert result["resume_permitted"] is False and calls == ["lookup", "lookup"]


def test_remote_matching_never_sends_local_origin_witnesses(monkeypatch):
    calls = []

    def call(operation, body, _timeout):
        calls.append((operation, body))
        return reply()

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: call)
    graph = definition(host="remote")
    graph["nodes"][0]["task"]["spec"]["options"] = {"origin_policies": ["private-local-witness"]}
    with authorization_scope(AuthorizationContext("caller", "admin")):
        result = inspect_agent_dag(graph)
    assert result["nodes"][0]["request_match"] == "unverifiable"
    assert calls == [("lookup", {"idempotency_key": "reviewed-one"})]


def test_owner_revocation_during_match_discards_proof(tmp_path, monkeypatch):
    store = UserStore(tmp_path / "users.json")
    store.add_user(user_id="caller", display_name="Caller", role="operator")
    calls = []

    def call(operation, body, _timeout):
        calls.append(operation)
        if "spec" in body:
            store.remove_user("caller")
        return reply(spec_match="matches")

    monkeypatch.setattr(managed_tasks, "_connection", lambda _host: call)
    owner = AuthorizationContext("caller", "operator", store_path=str(store.path))
    with authorization_scope(owner), pytest.raises(AuthorizationError):
        inspect_agent_dag(definition())
    assert calls == ["lookup", "lookup"]


def test_real_destination_matches_the_reviewed_skill_without_repeating_effects(tmp_path, monkeypatch):
    from je_auto_control.utils.admin import admin_client
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient
    from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
    from je_auto_control.utils.agent_runtime.runner import run_task

    target = FakeTarget()
    service = AgentRuntimeService(tmp_path / "service", targets={"fixture": target})
    service.start()
    graph = definition(host="remote")
    submitted = copy.deepcopy(graph["nodes"][0]["task"]["spec"])
    try:
        accepted = service.runtime.submit(submitted, idempotency_key="reviewed-one")
        assert run_task(service.runtime, accepted.task_id).state == "succeeded"
        metadata = json.loads((service.directory / "agent_runtime.json").read_text())
        console = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
        console.add_host("remote", metadata["url"], metadata["token"])
        monkeypatch.setattr(admin_client, "default_admin_console", lambda: console)
        with authorization_scope(AuthorizationContext("local-admin", "admin")):
            result = inspect_agent_dag(graph)
            changed = copy.deepcopy(graph)
            changed["nodes"][0]["task"]["spec"]["goal"] = "changed reviewed goal"
            different = inspect_agent_dag(changed)
        first = result["nodes"][0]
        assert first["request_match"] == "matches" and first["recorded_completion"] is True
        assert different["nodes"][0]["request_match"] == "differs"
        assert result["resume_permitted"] is False
        assert target.calls == ["AC_increment"] and len(service.runtime.list()) == 1
        assert not service.runtime._leases
    finally:
        service.close()
