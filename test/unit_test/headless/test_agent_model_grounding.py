"""Local models propose frame-local references; host geometry and verification remain authoritative."""
import json
from unittest.mock import patch

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskSpec, AgentObservationStale
from je_auto_control.utils.agent_runtime.ollama import OllamaTaskBackend
from je_auto_control.utils.agent_runtime.runner import run_task
from .test_agent_observed_targets import PointerTarget


def specification():
    return AgentTaskSpec.from_dict({"goal": "click observed button", "target": "pointer", "mode": "ollama",
        "allowed_tools": ["AC_click_mouse"], "options": {"model": "installed-local-model", "vision": True},
        "success_criteria": [{"kind": "result_equals", "key": "clicked", "value": True}]})


class ReplanningBackend:
    def __init__(self):
        self.decisions = 0

    def decide(self, _frame, receipts, **_kwargs):
        self.decisions += 1
        return {"stop": True} if receipts else {"tool": "AC_click_mouse",
            "arguments": {"mouse_keycode": "left"}, "reference": {"element_index": 0}}


class MovingTarget(PointerTarget):
    def __init__(self, *, always=False, safe=True):
        super().__init__()
        self.observations = 0
        self.always = always
        self.can_reobserve = safe

    def observe(self):
        self.observations += 1
        if self.always or self.observations == 2:
            self.frame["elements"][0]["bounds"][0] += 20
        return super().observe()


def test_model_gets_image_geometry_and_reference_schema_without_mutating_shared_tools():
    calls = []
    original = [{"type": "function", "function": {"name": "AC_click_mouse", "parameters": {
        "type": "object", "properties": {"mouse_keycode": {"type": "string"}, "x": {"type": "number"},
                                           "y": {"type": "number"}}, "required": ["mouse_keycode"]}}}]

    def transport(call):
        calls.append(call)
        if call["url"].endswith("/api/show"):
            value = {"capabilities": ["tools", "vision"]}
        else:
            value = {"message": {"tool_calls": [{"function": {"name": "AC_click_mouse", "arguments": {
                "mouse_keycode": "left", "observed_target": {"image_point": [10, 5]}}}}]}}
        return {"status": 200, "ok": True, "json": value}

    with patch("je_auto_control.utils.agent_runtime.transport.urllib_transport", transport):
        with patch("je_auto_control.utils.tool_use_schema.export_openai_tools", return_value=original):
            decision = OllamaTaskBackend(specification()).decide(PointerTarget().frame, [],
                                                                  timeout=1, check=lambda: None)
    assert decision["reference"] == {"image_point": [10, 5]}
    assert decision["arguments"] == {"mouse_keycode": "left"}
    payload = json.loads(calls[-1]["body"])
    content = json.loads(payload["messages"][1]["content"])
    assert content["observation"]["image_geometry"]["original_size"] == [400, 200]
    assert "data" not in content["observation"]["image_geometry"]
    offered = payload["tools"][0]["function"]["parameters"]["properties"]
    assert "observed_target" in offered and "observed_target" not in original[0]["function"]["parameters"]["properties"]


def test_model_reference_is_resolved_once_by_shared_runtime(tmp_path):
    target = PointerTarget()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"pointer": target})
    try:
        task = runtime.submit(specification())
        assert run_task(runtime, task.task_id, backend=ReplanningBackend()).state == "succeeded"
        assert target.calls == [("AC_click_mouse", {"mouse_keycode": "left", "x": -60, "y": 70})]
    finally:
        runtime.close()


def test_changed_observation_replans_within_retry_budget_without_replaying_input(tmp_path):
    target, backend = MovingTarget(), ReplanningBackend()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"pointer": target})
    try:
        task = runtime.submit(specification())
        assert run_task(runtime, task.task_id, backend=backend).state == "succeeded"
        assert target.calls == [("AC_click_mouse", {"mouse_keycode": "left", "x": -40, "y": 70})]
        assert len(runtime.store.actions(task.task_id)) == 1
    finally:
        runtime.close()


def test_continuous_geometry_change_exhausts_retries_without_preparing_any_effect(tmp_path):
    target, backend = MovingTarget(always=True), ReplanningBackend()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"pointer": target})
    try:
        task = runtime.submit(specification())
        assert run_task(runtime, task.task_id, backend=backend).state == "waiting_user"
        assert backend.decisions == 3 and target.calls == [] and runtime.store.actions(task.task_id) == []
    finally:
        runtime.close()


def test_adapter_without_safe_reobservation_does_not_replan_past_held_input(tmp_path):
    target, backend = MovingTarget(safe=False), ReplanningBackend()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"pointer": target})
    try:
        task = runtime.submit(specification())
        assert run_task(runtime, task.task_id, backend=backend).state == "waiting_user"
        assert backend.decisions == 1 and target.calls == []
    finally:
        runtime.close()


def test_stale_observation_error_round_trips_through_the_local_service(tmp_path):
    from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
    from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
    import pytest
    service = AgentRuntimeService(tmp_path, targets={"pointer": PointerTarget()})
    try:
        service.start()
        task = service.runtime.submit(specification())
        frame = service.runtime.observe(task.task_id)
        service.runtime.observe(task.task_id)
        client = AgentRuntimeClient(tmp_path / "agent_runtime.json")
        with pytest.raises(AgentObservationStale):
            client.call("act", {"task_id": task.task_id, "action": {"tool": "AC_click_mouse",
                "arguments": {"mouse_keycode": "left"}, "observation_id": frame.observation_id}})
    finally:
        service.close()
