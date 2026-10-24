"""Explicit source-owner recovery preserves evidence visibility and independently revocable review authority."""
from unittest.mock import Mock
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.dag import run_dag
from je_auto_control.utils.rbac.authorization import AuthorizationError, authorization_scope
from .test_agent_dag_local_tasks import owned as owned
from .test_agent_dag_batch_loopback import service as service
from .test_agent_dag_batches import graph
from .test_agent_dag_continuation import review, approval
from .test_agent_task_recovery import stopped as standalone_fixture

standalone = standalone_fixture


@pytest.fixture
def stopped(owned, monkeypatch):
    client, host, target, users, owner, actor, _unused = owned
    definition = graph()
    definition["nodes"][0]["task"]["spec"]["actions"] *= 2
    monkeypatch.setattr(host.runtime.background, "start", Mock())
    with authorization_scope(owner):
        batch = host.runtime.batches.control("register", {"definition": definition})
        started = host.runtime.batches.control("begin", {
            "batch_id": batch["batch_id"], "definition": definition, "max_parallel": 4})
        host.runtime.batches.control("claim", {
            "batch_id": batch["batch_id"], "attempt": started["attempt"], "node_id": "a"})
        task = started["definition"]["nodes"][0]["task"]
        original = host.runtime.batches.control("local_task", {
            "batch_id": batch["batch_id"], "attempt": started["attempt"], "node_id": "a",
            "operation": "submit", "body": {"spec": task["spec"], "idempotency_key": task["idempotency_key"]}})
        source = original["task_id"]
        frame = host.runtime.observe(source)
        host.runtime.act(source, {"tool": "AC_increment", "observation_id": frame.observation_id})
        host.runtime.pause(source)
        host.runtime.batches.control("pause_batch", {"batch_id": batch["batch_id"]})
    return client, host, target, users, owner, actor, batch, definition, source


def recovery(stopped, operation, request):
    client, _host, _target, _users, _owner, actor, _batch, _definition, _source = stopped
    with authorization_scope(actor):
        return client.call("recovery", {"operation": operation, "request": request})


def owned_request(stopped, *, reauthorize=False):
    operation = "review_authorization" if reauthorize else "preview"
    value = recovery(stopped, operation, {"task_id": stopped[-1], "owner_policy": "source_owner"})
    request = {"task_id": stopped[-1], "snapshot": value["snapshot"], "spec": value["draft"],
               "note": "Reviewed remainder and retained original ownership", "owner_policy": "source_owner",
               "ownership_review": value["ownership"]["review"]}
    if reauthorize:
        request["authorization_review"] = value["authorization_review"]
    return value, request


def test_admin_source_owned_child_is_adopted_without_broadening_reads(stopped, monkeypatch):
    client, host, target, _users, owner, actor, batch, definition, _source = stopped
    value, request = owned_request(stopped)
    assert value["ownership"]["owner"] == "owner" and value["ownership"]["actor"] == "reviewer"
    assert "store_path" not in str(value["ownership"])
    child = recovery(stopped, "create", request)["task_id"]
    assert recovery(stopped, "create", request)["task_id"] == child
    assert host.runtime.store.get(child)["owner"]["user_id"] == "owner"
    with authorization_scope(owner):
        assert run_task(host.runtime, child).state == "succeeded"
        assert client.call("get", {"task_id": child})["metadata"]["recovery"]["ownership"]["actor"] == "reviewer"
    jobs = host.runtime.background
    monkeypatch.setattr(jobs, "start", type(jobs).start.__get__(jobs))
    with authorization_scope(actor):
        selected = review(client, batch, definition)
        selected["decisions"][0] = {"node_id": "a", "action": "successor", "task_id": child}
        selected = review(client, batch, definition, decisions=selected["decisions"])
        assert selected["can_approve"]
        result = run_dag(definition, batch_id=batch["batch_id"], recovery=approval(selected))
    assert result.succeeded and target.count == 3


def test_default_admin_recovery_keeps_legacy_caller_ownership(stopped):
    value = recovery(stopped, "preview", {"task_id": stopped[-1]})
    assert "ownership" not in value
    request = {"task_id": stopped[-1], "snapshot": value["snapshot"], "spec": value["draft"], "note": "Reviewed"}
    child = recovery(stopped, "create", request)["task_id"]
    assert stopped[1].runtime.store.get(child)["owner"]["user_id"] == "reviewer"


@pytest.mark.parametrize("fault", ["missing_review", "wrong_review", "arbitrary_owner", "policy", "no_policy"])
def test_owned_recovery_rejects_unreviewed_and_caller_authored_identity(stopped, fault):
    _value, request = owned_request(stopped)
    if fault == "missing_review":
        request.pop("ownership_review")
    elif fault == "wrong_review":
        request["ownership_review"] = "forged"
    elif fault == "arbitrary_owner":
        request["owner"] = {"user_id": "other", "role": "admin"}
    elif fault == "policy":
        request["owner_policy"] = "arbitrary"
    else:
        request.pop("owner_policy")
    with pytest.raises(AgentTaskError):
        recovery(stopped, "create", request)
    assert len(stopped[1].runtime.list()) == 1 and stopped[2].count == 1


@pytest.mark.parametrize("user,role", [("owner", "viewer"), ("reviewer", "viewer"), ("reviewer", "operator")])
def test_queued_owned_successor_rechecks_both_principals_before_observation(stopped, user, role):
    _value, request = owned_request(stopped)
    child = recovery(stopped, "create", request)["task_id"]
    stopped[3].set_role(user, role)
    with authorization_scope(stopped[4]), pytest.raises(AuthorizationError):
        stopped[1].runtime.observe(child)
    assert stopped[2].count == 1


def test_maintenance_retires_owned_successor_when_reviewer_loses_cross_owner_authority(stopped):
    _value, request = owned_request(stopped)
    child = recovery(stopped, "create", request)["task_id"]
    with authorization_scope(stopped[4]):
        stopped[1].runtime.observe(child)
    stopped[3].set_role("reviewer", "operator")
    stopped[1].runtime.maintain()
    result = stopped[1].runtime.get(child)
    assert result.state == "cancelled" and result.metadata["input_released"] is True and stopped[2].count == 1


def test_revocation_during_grounding_cannot_reach_successor_input(stopped, monkeypatch):
    _value, request = owned_request(stopped)
    child = recovery(stopped, "create", request)["task_id"]
    instance, target, users, owner = stopped[1].runtime, stopped[2], stopped[3], stopped[4]
    original = target.observe

    def revoked():
        frame = original()
        users.set_role("reviewer", "operator")
        return frame

    with authorization_scope(owner):
        frame = instance.observe(child)
        monkeypatch.setattr(target, "observe", revoked)
        with pytest.raises(AuthorizationError):
            instance.act(child, {"tool": "AC_increment", "observation_id": frame.observation_id})
    assert target.count == 1 and [item["status"] for item in instance.store.actions(child)] == ["failed"]


@pytest.mark.parametrize("reauthorize", [False, True])
def test_owned_admission_failure_rolls_back_task_lineage_and_both_audits(stopped, reauthorize):
    _value, request = owned_request(stopped, reauthorize=reauthorize)
    with stopped[1].runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER fail_recovery_owner BEFORE INSERT ON agent_recovery_owners "
                           "BEGIN SELECT RAISE(ABORT,'fixture rollback'); END")
    with pytest.raises(AgentTaskError, match="database operation failed"):
        recovery(stopped, "create_authorized" if reauthorize else "create", request)
    with stopped[1].runtime.store.connection() as connection:
        for table in ("agent_task_recoveries", "agent_task_authorizations", "agent_recovery_owners"):
            assert connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
    assert len(stopped[1].runtime.list()) == 1 and stopped[2].count == 1


def test_owned_and_default_recovery_retries_cannot_switch_accepted_policy(stopped):
    _value, request = owned_request(stopped)
    recovery(stopped, "create", request)
    request.pop("owner_policy")
    request.pop("ownership_review")
    with pytest.raises(AgentTaskError, match="different ownership"):
        recovery(stopped, "create", request)


def test_reauthorized_owned_child_keeps_actual_actor_in_both_audits(stopped):
    _value, request = owned_request(stopped, reauthorize=True)
    result = recovery(stopped, "create_authorized", request)
    assert result["recovery"]["reauthorization"]["actor"] == "reviewer"
    assert result["recovery"]["ownership"]["owner"] == "owner"
    assert result["recovery"]["ownership"]["actor"] == "reviewer"


def test_restarted_runtime_keeps_original_ownership_and_reviewer_revocation_gate(stopped):
    _value, request = owned_request(stopped)
    child = recovery(stopped, "create", request)["task_id"]
    path = stopped[1].runtime.store.path
    stopped[1].close()
    stopped[3].set_role("reviewer", "operator")
    restored = AgentRuntime(path, targets={"fixture": stopped[2]})
    try:
        with authorization_scope(stopped[4]):
            assert restored.get(child).metadata["recovery"]["ownership"]["actor"] == "reviewer"
            assert restored.store.get(child)["owner"]["user_id"] == "owner"
            with pytest.raises(AuthorizationError):
                restored.observe(child)
        assert stopped[2].count == 1
    finally:
        restored.close()


def test_existing_caller_owned_child_is_not_backfilled_into_source_ownership(stopped):
    value = recovery(stopped, "preview", {"task_id": stopped[-1]})
    recovery(stopped, "create", {"task_id": stopped[-1], "snapshot": value["snapshot"],
                                "spec": value["draft"], "note": "Reviewed caller-owned successor"})
    _value, request = owned_request(stopped)
    with pytest.raises(AgentTaskError):
        recovery(stopped, "create", request)
    with stopped[1].runtime.store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_recovery_owners").fetchone()[0] == 0


def test_changed_live_owner_role_requires_a_fresh_ownership_review_even_when_input_is_still_allowed(stopped):
    _value, request = owned_request(stopped)
    stopped[3].set_role("owner", "admin")
    with pytest.raises(AgentTaskError, match="ownership changed"):
        recovery(stopped, "create", request)
    _value, fresh = owned_request(stopped)
    assert fresh["ownership_review"] != request["ownership_review"]
    assert recovery(stopped, "create", fresh)["state"] == "queued" and stopped[2].count == 1


def test_ownership_audit_outlives_child_retention_until_source_retention_cascades_it(standalone):
    instance, _target, source = standalone
    value = instance.recovery.control("preview", {"task_id": source, "owner_policy": "source_owner"})
    request = {"task_id": source, "owner_policy": "source_owner", "ownership_review": value["ownership"]["review"],
               "snapshot": value["snapshot"], "spec": value["draft"], "note": "Reviewed source ownership"}
    child = instance.recovery.control("create", request)["task_id"]
    with instance.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET state='cancelled',updated=?", (time.time() - 32 * 86400,))
    assert instance.prune()["deleted"] == [child]
    with instance.store.connection() as connection:
        assert connection.execute("SELECT 1 FROM agent_recovery_owners WHERE task_id=?", (child,)).fetchone()
    with pytest.raises(AgentTaskError):
        instance.recovery.control("create", request)
    assert instance.prune()["deleted"] == [source]
    with instance.store.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM agent_recovery_owners").fetchone()[0] == 0
