"""Explicit successor authorization replaces unavailable origins without reviving old grants."""
import pytest
import json
import time
from copy import deepcopy
from unittest.mock import Mock

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime import origin_policy
from je_auto_control.utils.agent_runtime.origin_policy import origin_scope
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from je_auto_control.utils.path_guard.policy import PathPolicy
from .test_agent_origin_policy import origin_directory as origin_directory
from .test_agent_runtime import FakeTarget, specification


@pytest.fixture
def retired_source(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    narrow = allowed / "reports"
    narrow.mkdir()
    old, current = PathPolicy([allowed]), PathPolicy([narrow])
    old_id, current_id = old.managed_origin(), current.managed_origin()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    with origin_scope(old_id):
        source = runtime.submit(specification(mode="skill", roots=[str(allowed)], actions=[
            {"tool": "AC_increment", "arguments": {"amount": 1}},
            {"tool": "AC_increment", "arguments": {"amount": 2}}],
            success_criteria=[{"kind": "result_equals", "key": "value", "value": 3}]))
        frame = runtime.observe(source.task_id)
        runtime.act(source.task_id, {"tool": "AC_increment", "arguments": {"amount": 1},
                                    "observation_id": frame.observation_id})
        runtime.pause(source.task_id)
    old.revoke_managed_origin()
    yield runtime, source.task_id, old_id, current_id, allowed, narrow
    runtime.close()


def reviewed_request(runtime, source):
    review = runtime.recovery.control("review_authorization", {"task_id": source})
    return {"task_id": source, "snapshot": review["snapshot"], "authorization_review": review["authorization_review"],
            "spec": review["draft"], "note": "Reapproved the original scope within the new session's report root"}


def test_reauthorized_child_is_narrower_and_does_not_revive_the_source_origin(retired_source):
    runtime, source, old_id, current_id, allowed, narrow = retired_source
    witness = origin_policy._path(old_id).read_bytes()
    with origin_scope(current_id):
        with pytest.raises(AgentTaskError, match="managed origin"):
            runtime.recovery.control("preview", {"task_id": source})
        request = reviewed_request(runtime, source)
        assert request["spec"]["roots"] == [str(narrow.resolve())]
        assert request["spec"]["options"]["origin_policies"] == [current_id]
        child = runtime.recovery.control("create_authorized", request)["task_id"]
        assert run_task(runtime, child).state == "succeeded"
        assert runtime.recovery.control("create_authorized", request)["task_id"] == child
    original = runtime.store.get(source)["spec"]
    assert original["roots"] == [str(allowed.resolve())]
    assert original["options"]["origin_policies"] == [old_id]
    assert origin_policy._path(old_id).read_bytes() == witness
    proof = runtime.get(child).metadata["recovery"]["reauthorization"]
    assert list(proof["approved_roots"]) == [str(narrow.resolve())]
    assert list(proof["context"]["replaced_origins"]) == [old_id]
    assert list(proof["context"]["current_origins"]) == [current_id]
    assert runtime.get(source).state == "paused"


@pytest.mark.parametrize("change", ["root", "model", "tools", "criteria", "old_origin", "review"])
def test_renewal_cannot_expand_scope_or_forge_approval(retired_source, change):
    runtime, source, old_id, current_id, allowed, _narrow = retired_source
    with origin_scope(current_id):
        request = reviewed_request(runtime, source)
        if change == "root":
            request["spec"]["roots"] = [str(allowed.parent)]
        elif change == "model":
            request["spec"]["options"]["model"] = "unapproved"
        elif change == "tools":
            request["spec"]["allowed_tools"].append("AC_write")
        elif change == "criteria":
            request["spec"]["success_criteria"] = [{"kind": "actions_complete"}]
        elif change == "old_origin":
            request["spec"]["options"]["origin_policies"] = [old_id]
        else:
            request["authorization_review"] = "0" * 64
        with pytest.raises(AgentTaskError):
            runtime.recovery.control("create_authorized", request)
    assert len(runtime.list()) == 1


def test_a_changed_new_origin_requires_another_authorization_review(retired_source):
    runtime, source, _old_id, current_id, allowed, _narrow = retired_source
    with origin_scope(current_id):
        request = reviewed_request(runtime, source)
        witness = origin_policy._path(current_id)
        import json
        state = json.loads(witness.read_text(encoding="utf-8"))
        state["roots"] = [str(allowed.resolve())]
        witness.write_text(json.dumps(state), encoding="utf-8")
        with pytest.raises(AgentTaskError, match="authorization.*changed"):
            runtime.recovery.control("create_authorized", request)
        assert len(runtime.list()) == 1


def test_a_newly_retired_caller_cannot_approve_its_own_replacement(retired_source):
    runtime, source, _old_id, current_id, _allowed, _narrow = retired_source
    with origin_scope(current_id):
        request = reviewed_request(runtime, source)
        witness = origin_policy._path(current_id)
        import json
        state = json.loads(witness.read_text(encoding="utf-8"))
        state["active"] = False
        witness.write_text(json.dumps(state), encoding="utf-8")
        with pytest.raises(AgentTaskError):
            runtime.recovery.control("create_authorized", request)
    assert len(runtime.list()) == 1


def test_available_old_ceilings_stay_bound_and_are_not_exposed_outside_the_source_root(retired_source):
    runtime, source, _old_id, current_id, allowed, narrow = retired_source
    retained = narrow / "retained"
    retained.mkdir()
    live = PathPolicy(use_client_roots=True)
    live.set_client_roots([allowed, allowed.parent / "unrelated-private-root"])
    live_id = live.managed_origin()
    data = runtime.store.get(source)["spec"]
    data["options"]["origin_policies"].append(live_id)
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET spec=? WHERE id=?", (json.dumps(data), source))
    live.set_client_roots([retained, allowed.parent / "unrelated-private-root"])
    with origin_scope(current_id):
        review = runtime.recovery.control("review_authorization", {"task_id": source})
        assert "unrelated-private-root" not in json.dumps(review)
        request = reviewed_request(runtime, source)
        assert request["spec"]["roots"] == [str(retained.resolve())]
        assert request["spec"]["options"]["origin_policies"] == [live_id, current_id]
        bad = deepcopy(request)
        bad["spec"]["options"]["origin_policies"] = [current_id]
        with pytest.raises(AgentTaskError):
            runtime.recovery.control("create_authorized", bad)
        live.revoke_managed_origin()
        with pytest.raises(AgentTaskError, match="authorization.*changed"):
            runtime.recovery.control("create_authorized", request)
    assert len(runtime.list()) == 1


def test_host_reapproval_without_a_client_origin_is_explicit_and_still_source_bounded(retired_source):
    runtime, source, old_id, _current_id, allowed, _narrow = retired_source
    request = reviewed_request(runtime, source)
    assert request["spec"]["roots"] == [str(allowed.resolve())]
    assert "origin_policies" not in request["spec"]["options"]
    child = runtime.recovery.control("create_authorized", request)["task_id"]
    proof = runtime.get(child).metadata["recovery"]["reauthorization"]
    assert proof["actor"] == "local" and list(proof["context"]["current_origins"]) == []
    assert list(proof["context"]["replaced_origins"]) == [old_id]


@pytest.mark.parametrize("state", ["missing", "corrupt"])
def test_unavailable_witnesses_are_reviewed_without_repairing_their_files(retired_source, state):
    runtime, source, old_id, current_id, _allowed, _narrow = retired_source
    path = origin_policy._path(old_id)
    if state == "missing":
        path.unlink()
    else:
        path.write_text("not a policy", encoding="utf-8")
    with origin_scope(current_id):
        request = reviewed_request(runtime, source)
        runtime.recovery.control("create_authorized", request)
    assert (path.read_text(encoding="utf-8") if path.exists() else None) == (
        "not a policy" if state == "corrupt" else None)


def test_current_session_change_and_ordinary_create_cannot_reuse_a_renewal_review(retired_source):
    runtime, source, _old_id, current_id, _allowed, narrow = retired_source
    with origin_scope(current_id):
        request = reviewed_request(runtime, source)
        with pytest.raises(AgentTaskError, match="invalid recovery"):
            runtime.recovery.control("create", request)
        plain = {key: value for key, value in request.items() if key != "authorization_review"}
        with pytest.raises(AgentTaskError, match="managed origin"):
            runtime.recovery.control("create", plain)
    another = PathPolicy([narrow])
    with origin_scope(another.managed_origin()), pytest.raises(AgentTaskError, match="authorization.*changed"):
        runtime.recovery.control("create_authorized", request)
    assert len(runtime.list()) == 1


def test_renewal_requires_reconciliation_and_never_bypasses_input_retirement(retired_source):
    runtime, source, _old_id, current_id, _allowed, _narrow = retired_source
    action = runtime.store.actions(source)[0]
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_actions SET status='uncertain' WHERE id=?", (action["id"],))
    with origin_scope(current_id):
        view = runtime.recovery.control("review_authorization", {"task_id": source})
        request = {"task_id": source, "snapshot": view["snapshot"],
                   "authorization_review": view["authorization_review"], "spec": view["review_template"],
                   "note": "Must reconcile the prior effect first"}
        with pytest.raises(AgentTaskError, match="reconcile unknown"):
            runtime.recovery.control("create_authorized", request)
        runtime.reconcile(source, {"action_id": action["id"], "decision": "applied", "result": {"value": 1},
                                  "note": "Independently checked the current application value"})
        with pytest.raises(AgentTaskError, match="snapshot changed"):
            runtime.recovery.control("create_authorized", request)
        request = reviewed_request(runtime, source)
        runtime._leases[source] = object()
        try:
            with pytest.raises(AgentTaskError, match="no active input"):
                runtime.recovery.control("create_authorized", request)
        finally:
            runtime._leases.clear()
    assert len(runtime.list()) == 1


def test_authorization_and_task_lineage_roll_back_together(retired_source):
    runtime, source, _old_id, current_id, _allowed, _narrow = retired_source
    with origin_scope(current_id):
        request = reviewed_request(runtime, source)
        with runtime.store.connection(write=True) as connection:
            connection.execute("CREATE TRIGGER reject_authorization BEFORE INSERT ON agent_task_authorizations "
                               "BEGIN SELECT RAISE(ABORT,'fixture authorization failure'); END")
        with pytest.raises(AgentTaskError):
            runtime.recovery.control("create_authorized", request)
        assert len(runtime.list()) == 1
        with runtime.store.connection(write=True) as connection:
            assert connection.execute("SELECT COUNT(*) FROM agent_task_recoveries").fetchone()[0] == 0
            connection.execute("DROP TRIGGER reject_authorization")
        assert runtime.recovery.control("create_authorized", request)["state"] == "queued"


def test_authorization_proof_survives_child_retention_until_source_cleanup(retired_source):
    runtime, source, _old_id, current_id, _allowed, _narrow = retired_source
    with origin_scope(current_id):
        child = runtime.recovery.control("create_authorized", reviewed_request(runtime, source))["task_id"]
        old = time.time() - 32 * 86400
        with runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE agent_tasks SET state='cancelled',updated=?", (old,))
        assert runtime.prune()["deleted"] == [child]
        view = runtime.recovery.control("review_authorization", {"task_id": source})
        assert view["existing_successor"]["task_id"] == child
        assert view["existing_successor"]["recovery"]["reauthorization"]["review"]
        assert runtime.prune()["deleted"] == [source]
        with runtime.store.connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM agent_task_authorizations").fetchone()[0] == 0


def test_only_the_owner_with_current_operator_authority_can_reauthorize(retired_source):
    runtime, source, _old_id, current_id, _allowed, _narrow = retired_source
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET owner=? WHERE id=?",
                           (json.dumps({"user_id": "alice", "role": "operator", "store_path": None}), source))
    with origin_scope(current_id), authorization_scope(AuthorizationContext("bob", "operator")):
        with pytest.raises(AgentTaskError, match="another caller"):
            reviewed_request(runtime, source)
    with origin_scope(current_id), authorization_scope(AuthorizationContext("alice", "operator")):
        request = reviewed_request(runtime, source)
    with origin_scope(current_id), authorization_scope(AuthorizationContext("alice", "viewer")):
        with pytest.raises(AuthorizationError):
            runtime.recovery.control("create_authorized", request)
    assert len(runtime.list()) == 1


@pytest.mark.parametrize("mode", ["external", "ollama"])
def test_dynamic_tasks_reauthorize_without_inventing_steps_or_contacting_a_model(retired_source, mode, monkeypatch):
    runtime, source, _old_id, current_id, _allowed, _narrow = retired_source
    data = runtime.store.get(source)["spec"]
    data.update(mode=mode, actions=[])
    if mode == "ollama":
        data["options"]["model"] = "fixture-tools"
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET spec=? WHERE id=?", (json.dumps(data), source))
    network = Mock(side_effect=AssertionError("authorization review contacted a model"))
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.ollama.request_json", network)
    with origin_scope(current_id):
        view = runtime.recovery.control("review_authorization", {"task_id": source})
        assert view["draft"] is None and view["completed_steps"] is None and view["remaining_actions"] == []
        spec = view["review_template"]
        assert spec["goal"] == "" and spec["mode"] == mode
        spec["goal"] = "Process only the remaining field under the new report scope"
        child = runtime.recovery.control("create_authorized", {"task_id": source, "snapshot": view["snapshot"],
            "authorization_review": view["authorization_review"], "spec": spec, "note": "Reviewed the new source"})
        assert runtime.store.actions(child["task_id"]) == []
    network.assert_not_called()


def test_inaccessible_completion_scope_produces_no_runnable_authorization_draft(retired_source):
    runtime, source, _old_id, current_id, allowed, _narrow = retired_source
    data = runtime.store.get(source)["spec"]
    data["success_criteria"] = [{"kind": "file_exists", "path": str(allowed / "outside-reports.txt")}]
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET spec=? WHERE id=?", (json.dumps(data), source))
    with origin_scope(current_id):
        view = runtime.recovery.control("review_authorization", {"task_id": source})
        assert view["draft"] is None and view["review_template"] is None
        assert view["issues"] == ["authorization_scope_unavailable"]
    assert len(runtime.list()) == 1


def test_approval_can_narrow_further_and_remains_bound_after_runtime_restart(retired_source):
    runtime, source, _old_id, current_id, _allowed, narrow = retired_source
    deeper = narrow / "one-job"
    deeper.mkdir()
    with origin_scope(current_id):
        request = reviewed_request(runtime, source)
        request["spec"]["roots"] = [str(deeper)]
        child = runtime.recovery.control("create_authorized", request)["task_id"]
    runtime.close()
    restored = AgentRuntime(runtime.store.path, targets={"fixture": FakeTarget()})
    try:
        with origin_scope(current_id):
            assert restored.recovery.control("create_authorized", request)["task_id"] == child
        proof = restored.get(child).metadata["recovery"]["reauthorization"]
        assert list(proof["approved_roots"]) == [str(deeper.resolve())]
        assert len(restored.list()) == 2
    finally:
        restored.close()
