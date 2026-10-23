"""Host-grounded observation references use fixed geometry and never dispatch native input."""
from copy import deepcopy
import base64
import io

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError


class PointerTarget:
    can_reobserve = True

    def __init__(self):
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", (200, 100), "white").save(buffer, format="JPEG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        self.calls = []
        self.frame = {"identity": {"window": 123, "process": 456},
            "elements": [{"index": 0, "bounds": [-100, 50, 80, 40], "native_id": "button", "enabled": True}],
            "image": {"origin": [-200, 0], "original_size": [400, 200], "image_size": [200, 100],
                      "format": "jpeg", "redacted_by": "strict", "data": encoded}}

    def ready(self, _spec):
        return True, ""

    def observe(self):
        return deepcopy(self.frame)

    def perform(self, tool, arguments):
        self.calls.append((tool, arguments))
        return {"clicked": True}

    def cleanup(self):
        return None


@pytest.fixture
def managed(tmp_path):
    target = PointerTarget()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"pointer": target})
    task = runtime.submit({"goal": "click observed target", "target": "pointer", "allowed_tools": ["AC_click_mouse"],
        "success_criteria": [{"kind": "result_equals", "key": "clicked", "value": True}]})
    yield runtime, target, task.task_id
    runtime.close()


def test_element_index_is_resolved_by_the_host_and_receipt_keeps_geometry_provenance(managed):
    runtime, target, task_id = managed
    frame = runtime.observe(task_id)
    runtime.act(task_id, {"tool": "AC_click_mouse", "arguments": {"mouse_keycode": "left"},
                          "reference": {"element_index": 0}, "observation_id": frame.observation_id})
    assert target.calls == [("AC_click_mouse", {"mouse_keycode": "left", "x": -60, "y": 70})]
    receipt = runtime.receipts(task_id)["actions"][0]
    assert receipt["grounding"]["reference"] == {"element_index": 0}
    assert receipt["grounding"]["observation_id"] == frame.observation_id
    assert receipt["grounding"]["requested_arguments"] == {"mouse_keycode": "left"}
    assert receipt["grounding"]["element"]["native_id"] == "button"
    assert "data" not in str(receipt["grounding"].get("image_geometry", {}))


def test_image_point_converts_thumbnail_pixels_to_native_coordinates_with_negative_origin(managed):
    runtime, target, task_id = managed
    frame = runtime.observe(task_id)
    runtime.act(task_id, {"tool": "AC_click_mouse", "arguments": {"mouse_keycode": "left"},
                          "reference": {"image_point": [10.5, 5]},
                          "observation_id": frame.observation_id})
    assert target.calls == [("AC_click_mouse", {"mouse_keycode": "left", "x": -179, "y": 10})]


@pytest.mark.parametrize("reference", [{"element_index": -1}, {"element_index": True}, {"element_index": 9},
    {"element_index": "0"}, {"image_point": [-1, 0]}, {"image_point": [200, 5]},
    {"image_point": [0, 100]}, {"image_point": [True, 0]}, {"image_point": [0]},
    {"image_point": [10 ** 400, 0]},
    {"element_index": 0, "image_point": [1, 1]}, {"unknown": 0}])
def test_invalid_or_outside_observation_references_never_dispatch(managed, reference):
    runtime, target, task_id = managed
    frame = runtime.observe(task_id)
    with pytest.raises(AgentTaskError):
        runtime.act(task_id, {"tool": "AC_click_mouse", "reference": reference,
                              "observation_id": frame.observation_id})
    assert target.calls == [] and runtime.store.actions(task_id) == []


def test_reference_and_explicit_coordinates_cannot_conflict(managed):
    runtime, target, task_id = managed
    frame = runtime.observe(task_id)
    with pytest.raises(AgentTaskError, match="coordinates"):
        runtime.act(task_id, {"tool": "AC_click_mouse", "arguments": {"x": 1, "y": 2},
                              "reference": {"element_index": 0}, "observation_id": frame.observation_id})
    assert target.calls == []


def test_changed_geometry_invalidates_old_reference_before_side_effect(managed):
    runtime, target, task_id = managed
    frame = runtime.observe(task_id)
    target.frame["elements"][0]["bounds"][0] += 20
    with pytest.raises(AgentTaskError, match="changed"):
        runtime.act(task_id, {"tool": "AC_click_mouse", "reference": {"element_index": 0},
                              "observation_id": frame.observation_id})
    assert target.calls == []


def test_incomplete_image_geometry_and_disabled_elements_fail_closed(managed):
    runtime, target, task_id = managed
    target.frame["elements"][0]["enabled"] = False
    frame = runtime.observe(task_id)
    with pytest.raises(AgentTaskError, match="disabled"):
        runtime.act(task_id, {"tool": "AC_click_mouse", "reference": {"element_index": 0},
                              "observation_id": frame.observation_id})
    target.frame["image"]["image_size"][0] = 0
    frame = runtime.observe(task_id)
    with pytest.raises(AgentTaskError, match="geometry"):
        runtime.act(task_id, {"tool": "AC_click_mouse", "reference": {"image_point": [0, 0]},
                              "observation_id": frame.observation_id})
    assert target.calls == []


def test_image_metadata_cannot_supply_a_different_scale_from_the_actual_pixels(managed):
    runtime, target, task_id = managed
    target.frame["image"]["image_size"] = [100, 50]
    frame = runtime.observe(task_id)
    with pytest.raises(AgentTaskError, match="actual pixels"):
        runtime.act(task_id, {"tool": "AC_click_mouse", "arguments": {"mouse_keycode": "left"},
                              "reference": {"image_point": [10, 5]}, "observation_id": frame.observation_id})
    assert target.calls == [] and runtime.store.actions(task_id) == []


def test_legacy_explicit_coordinates_are_preserved(managed):
    runtime, target, task_id = managed
    frame = runtime.observe(task_id)
    runtime.act(task_id, {"tool": "AC_click_mouse", "arguments": {"mouse_keycode": "left", "x": 1, "y": 2},
                          "observation_id": frame.observation_id})
    assert target.calls == [("AC_click_mouse", {"mouse_keycode": "left", "x": 1, "y": 2})]


def test_skill_completion_matches_requested_reference_and_keeps_actual_coordinates(tmp_path):
    from je_auto_control.utils.agent_runtime.runner import run_task
    target = PointerTarget()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"pointer": target})
    try:
        task = runtime.submit({"goal": "click indexed button", "target": "pointer", "mode": "skill",
            "allowed_tools": ["AC_click_mouse"], "actions": [{"tool": "AC_click_mouse",
                "arguments": {"mouse_keycode": "left"}, "reference": {"element_index": 0}}],
            "success_criteria": [{"kind": "actions_complete"},
                                 {"kind": "result_equals", "key": "clicked", "value": True}]})
        assert run_task(runtime, task.task_id).state == "succeeded"
        assert runtime.store.actions(task.task_id)[0]["arguments"]["x"] == -60
    finally:
        runtime.close()
    reopened = AgentRuntime(tmp_path / "tasks.sqlite", targets={"pointer": PointerTarget()})
    try:
        receipt = reopened.receipts(task.task_id)["actions"][0]
        assert receipt["grounding"]["reference"] == {"element_index": 0}
        assert receipt["arguments"]["x"] == -60
    finally:
        reopened.close()
