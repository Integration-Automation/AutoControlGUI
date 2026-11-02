"""Managed skill recording/version publication uses deterministic application fakes only."""
import json

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.agent_runtime.skill_parameters import parameter_schema, instantiate
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


class Editor:
    def __init__(self):
        self.calls = []

    def ready(self, _spec):
        return True, ""

    def observe(self):
        return {"identity": "editor", "elements": []}

    def perform(self, tool, arguments):
        self.calls.append((tool, arguments))
        return {"value": arguments["value"]}

    def cleanup(self):
        return None


@pytest.fixture
def managed(tmp_path):
    editor = Editor()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"editor": editor})
    yield runtime, editor
    runtime.close()


def source(runtime):
    task = runtime.submit({"goal": "set field", "target": "editor", "apps": ["Editor"],
        "allowed_tools": ["AC_edit"], "success_criteria": [{"kind": "result_equals", "key": "value", "value": "done"}]})
    frame = runtime.observe(task.task_id)
    runtime.act(task.task_id, {"tool": "AC_edit", "observation_id": frame.observation_id,
        "arguments": {"selector": {"name": "Old field", "role": "Edit", "app_name": "Editor"}, "value": "done"}})
    assert runtime.finish(task.task_id).state == "succeeded"
    return task.task_id


def record(runtime, **changes):
    return runtime.skills.control("record", {"task_id": source(runtime), "name": "set field", **changes})


def validate(runtime, candidate, **parameters):
    trial = runtime.skills.control("validate", {"candidate_id": candidate["id"], "parameters": parameters})
    assert run_task(runtime, trial["task_id"]).state == "succeeded"
    return trial["task_id"]


def publish(runtime, candidate, *, expected=0):
    trial = validate(runtime, candidate)
    return runtime.skills.control("accept", {"candidate_id": candidate["id"], "task_id": trial,
                                             "expected_version": expected, "note": "Reviewed exact candidate trial"})


def test_record_preview_validate_accept_and_run_pinned_version(managed):
    runtime, editor = managed
    slots = {"value": {"type": "string", "paths": ["/actions/0/arguments/value", "/success_criteria/0/value"]}}
    candidate = record(runtime, parameters=slots)
    preview = runtime.skills.control("preview", {"candidate_id": candidate["id"], "parameters": {"value": "Ada"}})
    assert preview["spec"]["actions"][0]["arguments"]["value"] == "Ada"
    assert candidate["spec"]["actions"][0]["arguments"]["value"] == "done"
    assert candidate["state"] == "draft" and candidate["version"] == 0
    accepted = publish(runtime, candidate)
    assert accepted["version"] == 1 and accepted["digest"] == candidate["digest"]
    assert accepted["publication"]["note"] == "Reviewed exact candidate trial"
    task = runtime.skills.control("run", {"skill_id": accepted["skill_id"], "version": 1,
                                            "parameters": {"value": "Grace"}})
    assert run_task(runtime, task["task_id"]).state == "succeeded"
    assert editor.calls[-1][1]["value"] == "Grace"
    assert runtime.store.get(task["task_id"])["spec"]["options"]["skill_pin"]["digest"] == candidate["digest"]


def test_candidate_never_publishes_from_unrelated_success_or_unfinished_trial(managed):
    runtime, _editor = managed
    candidate = record(runtime)
    unrelated = source(runtime)
    request = {"candidate_id": candidate["id"], "task_id": unrelated, "expected_version": 0, "note": "Reviewed"}
    with pytest.raises(AgentTaskError, match="exact candidate"):
        runtime.skills.control("accept", request)
    trial = runtime.skills.control("validate", {"candidate_id": candidate["id"]})
    request["task_id"] = trial["task_id"]
    with pytest.raises(AgentTaskError, match="verified success"):
        runtime.skills.control("accept", request)
    assert runtime.skills.control("get", {"candidate_id": candidate["id"]})["state"] == "draft"


def test_repairs_require_fresh_validation_and_do_not_change_running_snapshot(managed):
    runtime, editor = managed
    accepted = publish(runtime, record(runtime))
    task = runtime.skills.control("run", {"skill_id": accepted["skill_id"], "version": 1})
    repaired = runtime.skills.control("repair", {"candidate_id": accepted["id"], "note": "Field renamed",
        "changes": [{"path": "/actions/0/arguments/selector/name", "value": "New field"}]})
    replacement = publish(runtime, repaired, expected=1)
    assert replacement["version"] == 2
    assert runtime.get(task["task_id"]).metadata["skill_pin"]["version"] == 1
    assert run_task(runtime, task["task_id"]).state == "succeeded"
    assert editor.calls[-1][1]["selector"]["name"] == "Old field"
    new = runtime.skills.control("run", {"skill_id": accepted["skill_id"], "version": 2})
    assert run_task(runtime, new["task_id"]).state == "succeeded"
    assert editor.calls[-1][1]["selector"]["name"] == "New field"


def test_declared_pin_without_service_binding_is_not_presented_as_a_skill_version(managed):
    runtime, _editor = managed
    task = runtime.submit({"goal": "untrusted pin", "target": "editor", "allowed_tools": ["AC_edit"],
                          "options": {"skill_pin": {"version": 99}},
                          "success_criteria": [{"kind": "result_equals", "key": "value", "value": "done"}]})
    assert "skill_pin" not in runtime.get(task.task_id).metadata


def test_competing_repair_publication_requires_current_version(managed):
    runtime, _editor = managed
    accepted = publish(runtime, record(runtime))
    repairs = [runtime.skills.control("repair", {"candidate_id": accepted["id"], "note": "Reviewed rename",
        "changes": [{"path": "/actions/0/arguments/selector/name", "value": name}]}) for name in ("first", "second")]
    trials = [validate(runtime, item) for item in repairs]
    for index, candidate in enumerate(repairs):
        request = {"candidate_id": candidate["id"], "task_id": trials[index], "expected_version": 1, "note": "Reviewed"}
        if index == 0:
            assert runtime.skills.control("accept", request)["version"] == 2
        else:
            with pytest.raises(AgentTaskError, match="version changed"):
                runtime.skills.control("accept", request)


@pytest.mark.parametrize("pointer", ["/target", "/roots/0", "/allowed_tools/0", "/actions/0/tool",
                                    "/actions/0/arguments/selector/app_name", "/options/model"])
def test_repairs_cannot_change_scope_tools_or_application(managed, pointer):
    runtime, _editor = managed
    accepted = publish(runtime, record(runtime))
    with pytest.raises(AgentTaskError, match="semantic selector"):
        runtime.skills.control("repair", {"candidate_id": accepted["id"], "note": "Reviewed",
            "changes": [{"path": pointer, "value": "new"}]})


@pytest.mark.parametrize("pointer", ["/target", "/roots/0", "/apps/0", "/allowed_tools/0", "/actions/0/tool",
                                    "/budget/max_steps", "/options/allowed_origins/0"])
def test_parameter_slots_cannot_change_authority(managed, pointer):
    runtime, _editor = managed
    with pytest.raises(AgentTaskError, match="data values"):
        record(runtime, parameters={"bad": {"type": "string", "paths": [pointer]}})


def test_skill_owner_isolated_and_library_survives_runtime_restart(tmp_path):
    path = tmp_path / "skills.sqlite"
    runtime = AgentRuntime(path, targets={"editor": Editor()})
    try:
        with authorization_scope(AuthorizationContext("alice", "operator")):
            accepted = publish(runtime, record(runtime))
        with authorization_scope(AuthorizationContext("bob", "operator")):
            assert runtime.skills.control("list")["candidates"] == []
            with pytest.raises(AgentTaskError, match="another caller"):
                runtime.skills.control("get", {"candidate_id": accepted["id"]})
    finally:
        runtime.close()
    reopened = AgentRuntime(path, targets={"editor": Editor()})
    try:
        with authorization_scope(AuthorizationContext("alice", "operator")):
            task = reopened.skills.control("run", {"skill_id": accepted["skill_id"], "version": 1})
            assert run_task(reopened, task["task_id"]).state == "succeeded"
    finally:
        reopened.close()


def test_modified_trial_snapshot_and_candidate_digest_are_refused(managed):
    runtime, _editor = managed
    candidate = record(runtime)
    trial = validate(runtime, candidate)
    with runtime.store.connection(write=True) as connection:
        spec = runtime.store.get(trial)["spec"]
        spec["goal"] = "changed"
        connection.execute("UPDATE agent_tasks SET spec=? WHERE id=?", (json.dumps(spec), trial))
    with pytest.raises(AgentTaskError, match="exact candidate"):
        runtime.skills.control("accept", {"candidate_id": candidate["id"], "task_id": trial,
                                          "expected_version": 0, "note": "Reviewed"})
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_skill_candidates SET spec='{}' WHERE id=?", (candidate["id"],))
    with pytest.raises(AgentTaskError, match="digest mismatch"):
        runtime.skills.control("get", {"candidate_id": candidate["id"]})


def test_parameter_values_are_literals_typed_and_nonoverlapping():
    spec = {"actions": [{"arguments": {"value": 1}}], "inputs": {}, "success_criteria": []}
    slots = {"amount": {"type": "integer", "paths": ["/actions/0/arguments/value"]}}
    schema = parameter_schema(spec, slots)
    for value in (True, "2", 2.5):
        with pytest.raises(AgentTaskError, match="parameter"):
            instantiate(spec, schema, {"amount": value})
    with pytest.raises(AgentTaskError, match="unknown"):
        instantiate(spec, schema, {"other": 2})
    with pytest.raises(AgentTaskError, match="overlap"):
        parameter_schema(spec, {**slots, "again": slots["amount"]})
    with pytest.raises(AgentTaskError, match="literal data"):
        parameter_schema({"inputs": {"secret": "${secrets.PASSWORD}"}},
                         {"secret": {"type": "string", "paths": ["/inputs/secret"]}})


def test_parameterized_form_fill_and_readback_expectation_change_together():
    spec = {"actions": [{"arguments": {"value": "Ada"}}, {"expect_result": "Ada"}]}
    schema = parameter_schema(spec, {"name": {"type": "string", "paths": ["/actions/0/arguments/value",
                                                                           "/actions/1/expect_result"]}})
    materialized = instantiate(spec, schema, {"name": "Grace"})
    assert materialized["actions"][0]["arguments"]["value"] == "Grace"
    assert materialized["actions"][1]["expect_result"] == "Grace"
    assert spec["actions"][1]["expect_result"] == "Ada"


def test_recording_uses_actual_external_actions_instead_of_an_unexecuted_plan(managed):
    runtime, _editor = managed
    task_id = source(runtime)
    with runtime.store.connection(write=True) as connection:
        spec = runtime.store.get(task_id)["spec"]
        spec["actions"] = [{"tool": "AC_edit", "arguments": {"value": "never executed"}}]
        connection.execute("UPDATE agent_tasks SET spec=? WHERE id=?", (json.dumps(spec), task_id))
    candidate = runtime.skills.control("record", {"task_id": task_id, "name": "observed flow"})
    assert candidate["spec"]["actions"][0]["arguments"]["value"] == "done"


def test_failed_or_unproven_task_cannot_be_recorded(managed):
    runtime, _editor = managed
    task = runtime.submit({"goal": "unproven", "target": "editor", "allowed_tools": ["AC_edit"],
                          "success_criteria": [{"kind": "result_equals", "key": "value", "value": "done"}]})
    assert runtime.finish(task.task_id).state == "waiting_user"
    with pytest.raises(AgentTaskError, match="verified success"):
        runtime.skills.control("record", {"task_id": task.task_id, "name": "bad"})


def test_recording_does_not_invent_semantic_meaning_for_pointer_receipts(managed):
    runtime, _editor = managed
    task = runtime.submit({"goal": "pointer fixture", "target": "editor", "allowed_tools": ["AC_click_mouse"],
                          "success_criteria": [{"kind": "result_equals", "key": "value", "value": "done"}]})
    frame = runtime.observe(task.task_id)
    runtime.act(task.task_id, {"tool": "AC_click_mouse", "observation_id": frame.observation_id,
                               "arguments": {"x": 5, "y": 5, "value": "done"}})
    assert runtime.finish(task.task_id).state == "succeeded"
    with pytest.raises(AgentTaskError, match="reviewed selectors"):
        runtime.skills.control("record", {"task_id": task.task_id, "name": "bad pointer"})


def test_readback_mismatch_prevents_candidate_acceptance(managed):
    runtime, editor = managed
    candidate = record(runtime)
    original = editor.perform
    editor.perform = lambda *args: {"value": "wrong"}
    try:
        trial = runtime.skills.control("validate", {"candidate_id": candidate["id"]})
        assert run_task(runtime, trial["task_id"]).state == "waiting_user"
        with pytest.raises(AgentTaskError, match="verified success"):
            runtime.skills.control("accept", {"candidate_id": candidate["id"], "task_id": trial["task_id"],
                                              "expected_version": 0, "note": "Reviewed"})
    finally:
        editor.perform = original


def test_public_skill_api_and_http_service_share_verified_publication(tmp_path, monkeypatch):
    import threading
    import time
    from je_auto_control.utils.agent_runtime import api
    from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
    from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
    service = AgentRuntimeService(tmp_path, targets={"editor": Editor()})
    try:
        service.start()
        monkeypatch.setattr(api, "AgentRuntimeClient", lambda: AgentRuntimeClient(tmp_path / "agent_runtime.json"))
        candidate = api.manage_agent_skill("record", {"task_id": source(service.runtime), "name": "HTTP skill"})
        assert api.list_agent_skills()["candidates"][0]["id"] == candidate["id"]
        trial = api.manage_agent_skill("validate", {"candidate_id": candidate["id"]})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if api.get_agent_task(trial["task_id"])["state"] == "succeeded":
                break
            threading.Event().wait(0.1)  # At most 50 polls within the live service's request budget.
        accepted = api.manage_agent_skill("accept", {"candidate_id": candidate["id"], "task_id": trial["task_id"],
                                                   "expected_version": 0, "note": "Reviewed HTTP fake-target evidence"})
        assert accepted["version"] == 1 and accepted["publication"]["task_id"] == trial["task_id"]
    finally:
        service.close()
