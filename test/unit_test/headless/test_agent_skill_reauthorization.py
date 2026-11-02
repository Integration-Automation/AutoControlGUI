"""Published skill renewal creates a fresh candidate under bounded current authority."""
import json

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.origin_policy import origin_scope
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from .test_agent_skill_versions import Editor, publish
from .test_agent_origin_policy import origin_directory as origin_directory


@pytest.fixture
def published(tmp_path, origin_directory, request):
    allowed = tmp_path / "allowed"
    narrow = allowed / "reports"
    narrow.mkdir(parents=True)
    old = PathPolicy([allowed])
    old_id = old.managed_origin()
    current = PathPolicy([narrow])
    current_id = current.managed_origin()
    runtime = AgentRuntime(tmp_path / "agent_runtime.sqlite", targets={"editor": Editor()})
    criteria = [{"kind": "result_equals", "key": "value", "value": "done"}]
    if getattr(request, "param", None) == "outside_file":
        evidence = allowed / "original-evidence.txt"
        evidence.write_text("independent fixture evidence")
        criteria.append({"kind": "file_exists", "path": str(evidence)})
    try:
        with origin_scope(old_id):
            task = runtime.submit({"goal": "Set the reviewed field", "target": "editor", "apps": ["Editor"],
                "roots": [str(allowed)], "allowed_tools": ["AC_edit"],
                "success_criteria": criteria})
            frame = runtime.observe(task.task_id)
            runtime.act(task.task_id, {"tool": "AC_edit", "observation_id": frame.observation_id,
                "arguments": {"selector": {"name": "Field", "role": "Edit", "app_name": "Editor"},
                              "value": "done"}})
            assert runtime.finish(task.task_id).state == "succeeded"
            candidate = runtime.skills.control("record", {"task_id": task.task_id, "name": "Reviewed field",
                "parameters": {"value": {"type": "string", "paths": ["/actions/0/arguments/value",
                                                                         "/success_criteria/0/value"]}}})
            accepted = publish(runtime, candidate)
        old.revoke_managed_origin()
        yield runtime, accepted, old_id, current_id, allowed, narrow
    finally:
        runtime.close()


def approval(runtime, parent):
    view = runtime.skills.control("review_authorization", {"candidate_id": parent["id"]})
    return {"candidate_id": parent["id"], "snapshot": view["snapshot"], "spec": view["spec"],
            "authorization_review": view["authorization_review"], "note": "Reviewed remaining source limits"}


def test_renewal_requires_fresh_trial_and_publication_without_mutating_old_version(published):
    runtime, parent, old_id, current_id, _allowed, narrow = published
    with origin_scope(current_id):
        with pytest.raises(AgentTaskError, match="managed origin"):
            runtime.skills.control("run", {"skill_id": parent["skill_id"], "version": 1})
        request = approval(runtime, parent)
        assert request["spec"]["roots"] == [str(narrow)]
        candidate = runtime.skills.control("create_authorized", request)
        assert candidate["state"] == "draft" and candidate["version"] == 0
        assert candidate["parameters"] == parent["parameters"]
        assert candidate["spec"]["actions"] == parent["spec"]["actions"]
        assert candidate["provenance"]["reauthorization"]["context"]["replaced_origins"] == [old_id]
        assert runtime.skills.control("create_authorized", request)["id"] == candidate["id"]
        with pytest.raises(AgentTaskError, match="exact candidate"):
            runtime.skills.control("accept", {"candidate_id": candidate["id"],
                "task_id": parent["publication"]["task_id"], "expected_version": 1, "note": "Must not reuse trial"})
        accepted = publish(runtime, candidate, expected=1)
        task = runtime.skills.control("run", {"skill_id": parent["skill_id"], "version": 2,
                                             "parameters": {"value": "new value"}})
        assert run_task(runtime, task["task_id"]).state == "succeeded"
        assert accepted["version"] == 2
    assert runtime.skills.control("get", {"candidate_id": parent["id"]}) == parent


@pytest.mark.parametrize("change", ["roots", "actions", "criteria", "tools", "options", "digest", "snapshot"])
def test_renewal_rejects_widened_or_changed_plan_and_forged_review(published, change):
    runtime, parent, _old_id, current_id, allowed, _narrow = published
    with origin_scope(current_id):
        request = approval(runtime, parent)
        if change == "roots":
            request["spec"]["roots"] = [str(allowed.parent)]
        elif change == "actions":
            request["spec"]["actions"][0]["arguments"]["value"] = "different"
        elif change == "criteria":
            request["spec"]["success_criteria"][0]["value"] = "different"
        elif change == "tools":
            request["spec"]["allowed_tools"].append("AC_other")
        elif change == "options":
            request["spec"]["options"]["model"] = "unreviewed-model"
        else:
            request["authorization_review" if change == "digest" else "snapshot"] = "0" * 64
        with pytest.raises(AgentTaskError):
            runtime.skills.control("create_authorized", request)
    assert len(runtime.skills.control("list")["candidates"]) == 1


def test_context_changes_require_another_review_and_revoked_current_is_rejected(published):
    runtime, parent, _old_id, current_id, allowed, _narrow = published
    from je_auto_control.utils.agent_runtime import origin_policy
    with origin_scope(current_id):
        request = approval(runtime, parent)
        path = origin_policy._path(current_id)
        data = json.loads(path.read_text())
        data["roots"] = [str(allowed)]
        path.write_text(json.dumps(data))
        with pytest.raises(AgentTaskError, match="authorization.*changed"):
            runtime.skills.control("create_authorized", request)
        data["active"] = False
        path.write_text(json.dumps(data))
        with pytest.raises(AgentTaskError, match="managed origin"):
            runtime.skills.control("review_authorization", {"candidate_id": parent["id"]})


def test_owner_and_drive_capability_are_required_even_for_direct_review(published):
    runtime, parent, _old_id, current_id, _allowed, _narrow = published
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_skill_candidates SET owner=? WHERE id=?",
                           (json.dumps({"user_id": "alice", "store_path": None}), parent["id"]))
    with origin_scope(current_id), authorization_scope(AuthorizationContext("bob", "operator")):
        with pytest.raises(AgentTaskError, match="another caller"):
            approval(runtime, parent)
    with origin_scope(current_id), authorization_scope(AuthorizationContext("alice", "viewer")):
        with pytest.raises(AuthorizationError):
            approval(runtime, parent)


def test_failed_authorization_insert_rolls_back_candidate_and_retry_survives_restart(published):
    runtime, parent, _old_id, current_id, _allowed, _narrow = published
    with runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER fail_renew BEFORE INSERT ON agent_skill_authorizations "
                           "BEGIN SELECT RAISE(ABORT, 'fixture rollback'); END")
    with origin_scope(current_id):
        request = approval(runtime, parent)
        with pytest.raises(AgentTaskError, match="database operation failed"):
            runtime.skills.control("create_authorized", request)
        assert len(runtime.skills.control("list")["candidates"]) == 1
        with runtime.store.connection(write=True) as connection:
            connection.execute("DROP TRIGGER fail_renew")
        candidate = runtime.skills.control("create_authorized", request)
    runtime.close()
    restored = AgentRuntime(runtime.store.path, targets={"editor": Editor()})
    try:
        with origin_scope(current_id):
            assert restored.skills.control("create_authorized", request)["id"] == candidate["id"]
    finally:
        restored.close()


def test_review_never_creates_tasks_and_rejects_unpublished_or_superseded_sources(published):
    runtime, parent, _old_id, current_id, _allowed, _narrow = published
    before = runtime.list()
    with origin_scope(current_id):
        request = approval(runtime, parent)
        assert runtime.list() == before
        candidate = runtime.skills.control("create_authorized", request)
        with pytest.raises(AgentTaskError, match="current published"):
            approval(runtime, candidate)
        publish(runtime, candidate, expected=1)
        with pytest.raises(AgentTaskError, match="current published"):
            approval(runtime, parent)
        with pytest.raises(AgentTaskError, match="current published"):
            runtime.skills.control("create_authorized", request)


def test_still_live_old_restrictions_cannot_be_removed_and_unrelated_roots_are_clipped(published):
    runtime, parent, old_id, current_id, allowed, narrow = published
    from je_auto_control.utils.agent_runtime import origin_policy
    path = origin_policy._path(old_id)
    path.write_text(json.dumps({"version": 1, "active": True,
                                "roots": [str(narrow), str(allowed.parent / "unrelated-private-root")]}))
    with origin_scope(current_id):
        request = approval(runtime, parent)
        assert "unrelated-private-root" not in json.dumps(request)
        assert old_id in request["spec"]["options"]["origin_policies"]
        request["spec"]["options"]["origin_policies"].remove(old_id)
        with pytest.raises(AgentTaskError, match="preserve the entire plan"):
            runtime.skills.control("create_authorized", request)


@pytest.mark.parametrize("fault", ["empty_note", "extra_field", "missing_review", "different_session"])
def test_explicit_review_is_closed_and_session_bound(published, fault):
    runtime, parent, _old_id, current_id, _allowed, narrow = published
    with origin_scope(current_id):
        request = approval(runtime, parent)
    selected_id = current_id
    if fault == "empty_note":
        request["note"] = " "
    elif fault == "extra_field":
        request["parameters"] = {}
    elif fault == "missing_review":
        del request["authorization_review"]
    else:
        selected_id = PathPolicy([narrow]).managed_origin()
    with origin_scope(selected_id), pytest.raises(AgentTaskError):
        runtime.skills.control("create_authorized", request)


def test_further_narrowing_is_saved_with_actor_and_requires_no_original_trial_copy(published):
    runtime, parent, _old_id, current_id, _allowed, narrow = published
    deeper = narrow / "one-job"
    deeper.mkdir()
    with origin_scope(current_id), authorization_scope(AuthorizationContext("reviewer", "admin")):
        request = approval(runtime, parent)
        request["spec"]["roots"] = [str(deeper)]
        candidate = runtime.skills.control("create_authorized", request)
        proof = candidate["provenance"]["reauthorization"]
        assert proof["approved_roots"] == [str(deeper)]
        assert proof["actor"] == "reviewer"
        assert candidate["publication"] is None
        with runtime.store.connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM agent_skill_trials WHERE candidate_id=?",
                                      (candidate["id"],)).fetchone()[0] == 0


def test_concurrent_approval_callers_create_one_candidate(published):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    runtime, parent, _old_id, current_id, _allowed, _narrow = published
    barrier = Barrier(2)
    with origin_scope(current_id):
        request = approval(runtime, parent)

    def create(instance):
        with origin_scope(current_id):
            barrier.wait(timeout=10)
            return instance.skills.control("create_authorized", request)["id"]

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(create, (runtime, runtime)))
    assert results[0] == results[1]
    assert len(runtime.skills.control("list")["candidates"]) == 2


def test_publication_race_is_rechecked_in_the_candidate_insert_transaction(published, monkeypatch):
    runtime, parent, _old_id, current_id, _allowed, narrow = published
    deeper = narrow / "competitor"
    deeper.mkdir()
    with origin_scope(current_id):
        request = approval(runtime, parent)
        alternate = approval(runtime, parent)
        alternate["spec"]["roots"] = [str(deeper)]
        competitor = runtime.skills.control("create_authorized", alternate)
        original_save = runtime.skills._save

        def save_after_publication(*args):
            publish(runtime, competitor, expected=1)
            return original_save(*args)

        monkeypatch.setattr(runtime.skills, "_save", save_after_publication)
        with pytest.raises(AgentTaskError, match="version changed"):
            runtime.skills.control("create_authorized", request)
    assert len(runtime.skills.control("list")["candidates"]) == 2


@pytest.mark.parametrize("published", ["outside_file"], indirect=True)
def test_narrowed_scope_never_drops_an_inaccessible_completion_criterion(published):
    runtime, parent, _old_id, current_id, _allowed, _narrow = published
    with origin_scope(current_id):
        view = runtime.skills.control("review_authorization", {"candidate_id": parent["id"]})
        assert view["spec"] is None and view["issues"] == ["authorization_scope_unavailable"]
        assert view["approval_required"] and view["validation_required"]
    assert runtime.skills.control("get", {"candidate_id": parent["id"]}) == parent
