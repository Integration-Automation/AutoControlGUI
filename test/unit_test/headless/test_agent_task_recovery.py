"""Stopped-workflow successors require fresh approval and preserve source evidence without native input."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.routes import dispatch
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from .test_agent_runtime import FakeTarget, specification


@pytest.fixture
def stopped(tmp_path):
    target = FakeTarget()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": target})
    task = runtime.submit(specification(mode="skill", allowed_tools=["AC_increment"],
        actions=[{"tool": "AC_increment", "arguments": {"amount": 1}, "expect_result": {"value": 1}},
                 {"tool": "AC_increment", "arguments": {"amount": 2}, "expect_result": {"value": 3}}],
        success_criteria=[{"kind": "result_equals", "key": "value", "value": 3}, {"kind": "actions_complete"}]))
    frame = runtime.observe(task.task_id)
    runtime.act(task.task_id, {"tool": "AC_increment", "arguments": {"amount": 1},
                              "observation_id": frame.observation_id})
    runtime.pause(task.task_id)
    yield runtime, target, task.task_id
    runtime.close()


def preview(runtime, source):
    return runtime.recovery.control("preview", {"task_id": source})


def approval(runtime, source):
    result = preview(runtime, source)
    return {"task_id": source, "snapshot": result["snapshot"], "spec": result["draft"],
            "note": "Reviewed current application state and remaining work"}


def test_preview_is_passive_reports_progress_and_does_not_reuse_receipts(stopped, monkeypatch):
    runtime, target, source = stopped
    before = runtime.store.get(source), runtime.store.actions(source)
    monkeypatch.setattr(target, "ready", Mock(side_effect=AssertionError("target probe")))
    first = preview(runtime, source)
    assert first == preview(runtime, source)
    assert first["completed_steps"] == 1 and first["issues"] == []
    assert first["draft"]["actions"] == [{"tool": "AC_increment", "arguments": {"amount": 2},
                                         "expect_result": {"value": 3}}]
    assert first["approval_required"] is True and first["source_completion_inherited"] is False
    assert first["source_receipts"][0]["status"] == "confirmed"
    assert (runtime.store.get(source), runtime.store.actions(source)) == before
    assert target.calls == ["AC_increment"]


def test_new_successor_executes_only_reviewed_remaining_steps_and_keeps_parent_stopped(stopped):
    runtime, target, source = stopped
    request = approval(runtime, source)
    before = runtime.receipts(source)
    child = runtime.recovery.control("create", request)
    assert runtime.store.actions(child["task_id"]) == []
    assert child["recovery"]["source_task"] == source
    assert run_task(runtime, child["task_id"]).state == "succeeded"
    assert len(target.calls) == 2
    assert runtime.get(source).state == "paused" and runtime.receipts(source) == before
    with pytest.raises(AgentTaskError, match="reviewed successor"):
        runtime.resume(source)
    assert runtime.get(child["task_id"]).metadata["recovery"]["snapshot"] == request["snapshot"]
    assert runtime.recovery.control("create", request)["task_id"] == child["task_id"]


def test_historical_input_does_not_prove_new_application_state(stopped):
    runtime, target, source = stopped
    request = approval(runtime, source)
    target.value = 0
    child = runtime.recovery.control("create", request)
    assert run_task(runtime, child["task_id"]).state == "waiting_user"
    assert runtime.get(source).state == "paused"


@pytest.mark.parametrize("field,value", [("target", "other"), ("mode", "external"),
    ("allowed_tools", ["AC_increment", "AC_write"]), ("roots", ["D:/"]), ("inputs", {"new": "value"}),
    ("apps", ["other"]), ("options", {"automatic": True}),
    ("success_criteria", [{"kind": "actions_complete"}]), ("budget", {"max_steps": 99})])
def test_review_cannot_silently_change_source_authority_or_completion(stopped, field, value):
    runtime, _target, source = stopped
    request = approval(runtime, source)
    request["spec"][field] = value
    with pytest.raises(AgentTaskError):
        runtime.recovery.control("create", request)
    assert len(runtime.list()) == 1


@pytest.mark.parametrize("change", ["state", "receipt", "review"])
def test_changed_source_snapshot_requires_a_fresh_review(stopped, change):
    runtime, _target, source = stopped
    request = approval(runtime, source)
    if change == "state":
        runtime.store.update(source, "waiting_user", reason="new review")
    elif change == "receipt":
        with runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE agent_actions SET result='null' WHERE task_id=?", (source,))
    else:
        action = runtime.store.actions(source)[0]
        with runtime.store.connection(write=True) as connection:
            connection.execute("INSERT INTO agent_reviews VALUES (?,?,?,?,?,?,?)",
                               (action["id"], source, "applied", "new witness", "null", 1, "local"))
    with pytest.raises(AgentTaskError, match="snapshot changed"):
        runtime.recovery.control("create", request)


def test_unknown_effects_must_be_reconciled_and_are_never_discarded(stopped):
    runtime, _target, source = stopped
    action = runtime.store.actions(source)[0]
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_actions SET status='uncertain' WHERE id=?", (action["id"],))
    view = preview(runtime, source)
    assert view["draft"] is None and "unknown_source_effects" in view["issues"]
    request = {"task_id": source, "snapshot": view["snapshot"],
               "spec": deepcopy(runtime.store.get(source)["spec"]), "note": "Must not erase unknown input"}
    with pytest.raises(AgentTaskError, match="reconcile unknown"):
        runtime.recovery.control("create", request)
    runtime.reconcile(source, {"action_id": action["id"], "decision": "applied", "result": {"value": 1},
                               "note": "Independently checked the target's current value"})
    request = approval(runtime, source)
    child = runtime.recovery.control("create", request)
    assert child["task_id"] != source
    assert runtime.receipts(source)["reviews"][0]["original_result"] is not None


@pytest.mark.parametrize("replacement,issue", [
    ({"tool": "AC_increment", "arguments": {"amount": {"$capture": "old"}}}, "fresh_capture_required"),
    ({"tool": "AC_increment", "reference": {"element_index": 0}}, "fresh_semantic_grounding_required"),
])
def test_old_capture_values_and_observation_indexes_are_not_transplanted(stopped, replacement, issue):
    runtime, _target, source = stopped
    data = runtime.store.get(source)["spec"]
    data["actions"][1] = replacement
    with runtime.store.connection(write=True) as connection:
        import json
        connection.execute("UPDATE agent_tasks SET spec=? WHERE id=?", (json.dumps(data), source))
    view = preview(runtime, source)
    assert issue in view["issues"] and view["draft"] is None
    request = {"task_id": source, "snapshot": view["snapshot"], "spec": data, "note": "review"}
    with pytest.raises(AgentTaskError, match="fresh semantic actions"):
        runtime.recovery.control("create", request)


def test_simultaneous_repeated_approval_creates_one_child(stopped):
    runtime, _target, source = stopped
    request = approval(runtime, source)
    with ThreadPoolExecutor(max_workers=4) as workers:
        children = list(workers.map(lambda _index: runtime.recovery.control("create", request), range(4)))
    assert len({child["task_id"] for child in children}) == 1
    assert len(runtime.list()) == 2
    request["spec"]["actions"][0]["arguments"]["amount"] = 3
    with pytest.raises(AgentTaskError, match="different reviewed successor"):
        runtime.recovery.control("create", request)


def test_only_explicit_create_dispatches_background_work(stopped):
    runtime, _target, source = stopped
    runtime.background = SimpleNamespace(start=Mock())
    view = dispatch(runtime, "recovery", {"operation": "preview", "request": {"task_id": source}})
    runtime.background.start.assert_not_called()
    child = dispatch(runtime, "recovery", {"operation": "create", "request": {
        "task_id": source, "snapshot": view["snapshot"], "spec": view["draft"], "note": "reviewed"}})
    runtime.background.start.assert_called_once_with(child["task_id"])
    runtime.background = None


def test_successor_lineage_and_deduplication_survive_runtime_restart(stopped):
    runtime, _target, source = stopped
    request = approval(runtime, source)
    child = runtime.recovery.control("create", request)
    runtime.close()
    restored = AgentRuntime(runtime.store.path, targets={"fixture": FakeTarget()})
    try:
        assert restored.recovery.control("create", request)["task_id"] == child["task_id"]
        assert len(restored.list()) == 2
        assert restored.get(source).state == "paused"
        assert restored.get(child["task_id"]).metadata["recovery"]["source_task"] == source
    finally:
        restored.close()


def test_task_and_lineage_insert_roll_back_together(stopped):
    runtime, _target, source = stopped
    request = approval(runtime, source)
    with runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER reject_recovery BEFORE INSERT ON agent_task_recoveries "
                           "BEGIN SELECT RAISE(ABORT,'fixture transaction failure'); END")
    with pytest.raises(AgentTaskError):
        runtime.recovery.control("create", request)
    assert len(runtime.list()) == 1
    with runtime.store.connection(write=True) as connection:
        connection.execute("DROP TRIGGER reject_recovery")
    assert runtime.recovery.control("create", request)["state"] == "queued"


def test_lost_creation_reply_recovers_existing_task_without_duplicate_delivery(stopped, monkeypatch):
    runtime, _target, source = stopped
    request = approval(runtime, source)
    ensure = runtime.evidence.ensure
    monkeypatch.setattr(runtime.evidence, "ensure", Mock(side_effect=OSError("fixture lost reply")))
    with pytest.raises(OSError):
        runtime.recovery.control("create", request)
    assert len(runtime.store.list()) == 2
    monkeypatch.setattr(runtime.evidence, "ensure", ensure)
    child = runtime.recovery.control("create", request)
    assert len(runtime.list()) == 2
    assert runtime.get(child["task_id"]).metadata["history_id"] != runtime.get(source).metadata["history_id"]


def test_retention_preserves_parent_evidence_until_the_successor_is_retired(stopped):
    runtime, _target, source = stopped
    child = runtime.recovery.control("create", approval(runtime, source))["task_id"]
    old = time.time() - 32 * 86400
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET state='cancelled',updated=? WHERE id=?", (old, source))
    assert runtime.prune()["deleted"] == []
    assert runtime.receipts(source)["total"] == 1
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET state='cancelled',updated=? WHERE id=?", (old, child))
    assert runtime.prune()["deleted"] == [child]
    with pytest.raises(AgentTaskError):
        runtime.recovery.control("create", approval(runtime, source))
    assert runtime.prune()["deleted"] == [source]


def test_recovery_does_not_steal_an_unretired_input_lease(stopped):
    runtime, _target, source = stopped
    request = approval(runtime, source)
    runtime._leases[source] = object()
    try:
        with pytest.raises(AgentTaskError, match="no active input"):
            preview(runtime, source)
        with pytest.raises(AgentTaskError, match="no active input"):
            runtime.recovery.control("create", request)
    finally:
        runtime._leases.clear()


def test_owner_and_operator_authority_are_required_for_recovery(tmp_path):
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        with authorization_scope(AuthorizationContext("alice", "operator")):
            task = runtime.submit(specification(mode="skill", actions=[{"tool": "AC_increment"}]))
            runtime.pause(task.task_id)
            request = approval(runtime, task.task_id)
        with authorization_scope(AuthorizationContext("bob", "operator")):
            with pytest.raises(AgentTaskError, match="another caller"):
                preview(runtime, task.task_id)
        with authorization_scope(AuthorizationContext("alice", "viewer")):
            with pytest.raises(AuthorizationError):
                runtime.recovery.control("create", request)
        with authorization_scope(AuthorizationContext("alice", "operator")):
            assert runtime.recovery.control("create", request)["state"] == "queued"
    finally:
        runtime.close()


def test_caller_request_keys_cannot_preclaim_or_supply_a_recovery_successor(stopped):
    runtime, _target, source = stopped
    request = approval(runtime, source)
    preclaimed = runtime.submit(request["spec"], idempotency_key="recovery:" + source + ":" + request["snapshot"])
    runtime.store.update(preclaimed.task_id, "succeeded",
                         verification=[{"kind": "actions_complete", "status": "passed"}])
    child = runtime.recovery.control("create", request)
    assert child["task_id"] != preclaimed.task_id
    assert child["state"] == "queued" and runtime.store.actions(child["task_id"]) == []
    assert child["recovery"]["source_task"] == source
