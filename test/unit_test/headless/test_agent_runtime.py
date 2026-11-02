"""Managed tasks use isolated fakes; no desktop input or capture is permitted."""
import pytest

from je_auto_control.utils.agent_runtime import AgentTaskSpec, AgentRuntime, AgentTaskError


class FakeTarget:
    """A deterministic application whose state is an in-memory counter."""

    def __init__(self):
        self.value = 0
        self.calls = []

    def observe(self):
        return {"identity": "fixture", "elements": [{"name": str(self.value)}], "geometry": [0, 0, 100, 100]}

    def ready(self, _spec):
        return True, ""

    def perform(self, name, arguments):
        self.calls.append(name)
        self.value += int(arguments.get("amount", 1))
        return {"value": self.value}

    def cleanup(self):
        return None


def specification(**changes):
    values = {"goal": "increment", "target": "fixture", "allowed_tools": ["AC_increment"],
              "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}]}
    values.update(changes)
    return AgentTaskSpec.from_dict(values)


@pytest.fixture
def managed(tmp_path):
    target = FakeTarget()
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": target})
    yield runtime, target
    runtime.close()


def test_specification_is_detached_and_requires_real_completion_conditions():
    raw = {"goal": "work", "allowed_tools": ["AC_increment"],
           "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}]}
    spec = AgentTaskSpec.from_dict(raw)
    raw["success_criteria"][0]["value"] = 99
    assert spec.to_dict()["success_criteria"][0]["value"] == 1
    with pytest.raises(AgentTaskError):
        AgentTaskSpec.from_dict({"goal": "work"})


def test_external_task_observe_act_verify(managed):
    runtime, target = managed
    task = runtime.submit(specification())
    frame = runtime.observe(task.task_id)
    outcome = runtime.act(task.task_id, {"tool": "AC_increment", "arguments": {},
                                         "observation_id": frame.observation_id})
    assert outcome.result == {"value": 1}
    assert target.calls == ["AC_increment"]
    result = runtime.finish(task.task_id)
    assert result.state == "succeeded"
    assert result.verification[0]["status"] == "passed"


def test_model_completion_is_not_evidence(managed):
    runtime, _target = managed
    task = runtime.submit(specification())
    assert runtime.finish(task.task_id).state == "waiting_user"


def test_old_observation_never_drives_input(managed):
    runtime, target = managed
    task = runtime.submit(specification())
    old = runtime.observe(task.task_id)
    runtime.observe(task.task_id)
    with pytest.raises(AgentTaskError, match="observation"):
        runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": old.observation_id})
    assert target.calls == []


def test_changed_target_rejects_old_observation(managed):
    runtime, target = managed
    task = runtime.submit(specification())
    old = runtime.observe(task.task_id)
    target.value = 9
    with pytest.raises(AgentTaskError, match="observation"):
        runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": old.observation_id})
    assert target.calls == []


def test_cancel_releases_control_and_never_runs_more_actions(managed):
    runtime, target = managed
    first = runtime.submit(specification())
    frame = runtime.observe(first.task_id)
    assert runtime.cancel(first.task_id).state == "cancelled"
    with pytest.raises(AgentTaskError):
        runtime.act(first.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
    second = runtime.submit(specification())
    assert runtime.observe(second.task_id).observation_id
    assert target.calls == []


def test_task_scope_rejects_unoffered_tool(managed):
    runtime, target = managed
    task = runtime.submit(specification())
    frame = runtime.observe(task.task_id)
    with pytest.raises(AgentTaskError, match="allowed"):
        runtime.act(task.task_id, {"tool": "AC_shell_command", "observation_id": frame.observation_id})
    assert target.calls == []


def test_second_task_waits_for_target_owner(managed):
    runtime, _target = managed
    one, two = runtime.submit(specification()), runtime.submit(specification())
    runtime.observe(one.task_id)
    with pytest.raises(AgentTaskError, match="control"):
        runtime.observe(two.task_id)
    runtime.pause(one.task_id)
    assert runtime.observe(two.task_id).observation_id


def test_restart_preserves_uncertain_actions_without_replaying(tmp_path):
    db = tmp_path / "runtime.sqlite"
    target = FakeTarget()
    runtime = AgentRuntime(db, targets={"fixture": target})
    task = runtime.submit(specification())
    frame = runtime.observe(task.task_id)
    runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
    runtime.close()
    restored = AgentRuntime(db, targets={"fixture": target})
    try:
        assert restored.get(task.task_id).state == "recovering"
        assert target.calls == ["AC_increment"]
        restored.resume(task.task_id)
        assert restored.finish(task.task_id).state == "succeeded"
        assert target.calls == ["AC_increment"]
    finally:
        restored.close()


def test_task_results_are_private_to_owner(managed):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
    runtime, _target = managed
    with authorization_scope(AuthorizationContext("alice", "operator")):
        task = runtime.submit(specification())
    with authorization_scope(AuthorizationContext("bob", "operator")):
        with pytest.raises(AgentTaskError, match="owner"):
            runtime.get(task.task_id)


def test_file_completion_cannot_escape_task_roots(managed, tmp_path):
    runtime, _target = managed
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    root = tmp_path / "allowed"
    root.mkdir()
    with pytest.raises(AgentTaskError, match="root"):
        runtime.submit(specification(roots=[str(root)],
                                     success_criteria=[{"kind": "file_exists", "path": str(outside)}]))


def test_pause_does_not_transfer_control_before_running_action_retires(managed):
    import threading
    runtime, target = managed
    entered, release = threading.Event(), threading.Event()
    original = target.perform

    def slow(name, args):
        entered.set()
        assert release.wait(5)
        return original(name, args)

    target.perform = slow
    first, second = runtime.submit(specification()), runtime.submit(specification())
    frame = runtime.observe(first.task_id)
    worker = threading.Thread(target=lambda: runtime.act(first.task_id, {
        "tool": "AC_increment", "observation_id": frame.observation_id}))
    worker.start()
    assert entered.wait(5)
    try:
        assert runtime.pause(first.task_id).state == "pausing"
        with pytest.raises(AgentTaskError, match="control"):
            runtime.observe(second.task_id)
    finally:
        release.set()
        worker.join(5)
    assert runtime.get(first.task_id).state == "paused"
    assert runtime.observe(second.task_id).observation_id


def test_final_allowed_step_can_still_be_verified(managed):
    runtime, _target = managed
    task = runtime.submit(specification(budget={"max_steps": 1}))
    frame = runtime.observe(task.task_id)
    runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
    assert runtime.finish(task.task_id).state == "succeeded"


def test_paused_task_requires_explicit_resume(managed):
    runtime, target = managed
    task = runtime.submit(specification())
    runtime.observe(task.task_id)
    runtime.pause(task.task_id)
    with pytest.raises(AgentTaskError, match="paused"):
        runtime.observe(task.task_id)
    runtime.resume(task.task_id)
    assert runtime.observe(task.task_id).observation_id
    assert target.calls == []


def test_expired_task_releases_target_after_cleanup(managed):
    import time
    runtime, _target = managed
    first = runtime.submit(specification())
    runtime.observe(first.task_id)
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET started=? WHERE id=?", (time.time() - 1000, first.task_id))
    with pytest.raises(AgentTaskError, match="budget"):
        runtime.observe(first.task_id)
    assert runtime.get(first.task_id).state == "timed_out"
    second = runtime.submit(specification())
    assert runtime.observe(second.task_id).observation_id


def test_step_budget_exhaustion_does_not_pin_input_owner(managed):
    runtime, _target = managed
    task = runtime.submit(specification(budget={"max_steps": 1}))
    frame = runtime.observe(task.task_id)
    runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
    frame = runtime.observe(task.task_id)
    with pytest.raises(AgentTaskError, match="budget"):
        runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
    assert runtime.get(task.task_id).state == "failed"
    second = runtime.submit(specification())
    assert runtime.observe(second.task_id).observation_id
