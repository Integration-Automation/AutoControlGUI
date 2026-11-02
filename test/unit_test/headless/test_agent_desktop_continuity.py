"""Desktop form prefixes also require live target state; every application and control here is fake."""
from contextlib import closing

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskSpec, AgentTargetProfile, AgentHumanReview
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.agent_runtime.targets import DesktopTarget
from .test_agent_workflows import Applications


class ContextualApplications(Applications, DesktopTarget):
    def __init__(self):
        Applications.__init__(self)
        DesktopTarget.__init__(self)

    def ready(self, spec):
        self._spec = spec
        return True, ""

    def cleanup(self):
        DesktopTarget.cleanup(self)


def form():
    return AgentTaskSpec.from_dict({"goal": "fill reviewed form", "target": "local-desktop", "mode": "skill",
        "apps": ["fixture"], "allowed_tools": ["AC_workflow_control"],
        "actions": [{"tool": "AC_workflow_control", "arguments": {"operation": "set", "selector": {
            "name": "Field", "app_name": "fixture"}, "value": "reviewed"}, "expect_result": True},
            {"tool": "AC_workflow_control", "arguments": {"operation": "invoke", "selector": {
                "name": "Save", "app_name": "fixture"}}, "expect_result": True}],
        "success_criteria": [{"kind": "actions_complete"}]})


def test_retired_desktop_context_cannot_submit_an_edited_form_after_pause(tmp_path):
    target = ContextualApplications()
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"local-desktop": target})) as runtime:
        task = runtime.submit(form())
        observed = runtime.observe(task.task_id)
        action = form().to_dict()["actions"][0]
        runtime.act(task.task_id, {"tool": action["tool"], "arguments": action["arguments"],
                                  "observation_id": observed.observation_id})
        runtime.pause(task.task_id)
        target.values["Field"] = "changed while paused"
        runtime.resume(task.task_id)
        outcome = run_task(runtime, task.task_id)
        assert outcome.state == "waiting_user" and "desktop context" in outcome.reason
        assert target.submissions == 0
        assert len(runtime.store.actions(task.task_id)) == 1


def test_profiled_desktop_prefix_is_refused_before_any_helper_launch():
    profile = AgentTargetProfile(name="reviewed-desktop", kind="desktop", apps=("fixture",),
        allowed_tools=("AC_workflow_control",), settings={"platform": "windows"})
    target = NativeDesktopTarget(profile=profile.to_dict())
    with pytest.raises(AgentHumanReview, match="desktop context"):
        target.check_resume(form(), [{"status": "confirmed"}])
    assert target._channel is None and target._resource is None


def test_uninterrupted_desktop_skill_keeps_its_context(tmp_path):
    target = ContextualApplications()
    with closing(AgentRuntime(tmp_path / "runtime.sqlite", targets={"local-desktop": target})) as runtime:
        task = runtime.submit(form())
        assert run_task(runtime, task.task_id).state == "succeeded"
        assert target.submissions == 1
