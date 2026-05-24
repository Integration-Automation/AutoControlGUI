"""Tests for the Anthropic computer-use agent backend.

The backend is tested against a stubbed Anthropic client so no real API
key is required. The stub records every call and replays canned
``content`` blocks, exercising every action-verb translation path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from je_auto_control.utils.agent.agent_loop import AgentStep
from je_auto_control.utils.agent.backends.anthropic_computer_use import (
    ComputerUseAgentBackend, _decision_from_computer_action, _parse_combo,
)
from je_auto_control.utils.agent.backends.base import AgentBackendError


# --- helpers --------------------------------------------------------

@dataclass
class _StubBlock:
    type: str
    id: Optional[str] = None
    name: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    text: Optional[str] = None


class _StubResponse:
    def __init__(self, content):
        self.content = content


class _StubMessages:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.script: List[_StubResponse] = []

    def queue(self, response: _StubResponse) -> None:
        self.script.append(response)

    def create(self, **kwargs) -> _StubResponse:
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("stub client exhausted")
        return self.script.pop(0)


class _StubClient:
    def __init__(self):
        self.messages = _StubMessages()


def _backend(client: Optional[_StubClient] = None):
    return ComputerUseAgentBackend(
        display_width_px=1920,
        display_height_px=1080,
        client=client or _StubClient(),
    )


# --- action translation ---------------------------------------------

@pytest.mark.parametrize("payload,expected", [
    ({"action": "screenshot"}, {"tool": "AC_screenshot", "input": {}}),
    ({"action": "cursor_position"},
     {"tool": "AC_get_mouse_position", "input": {}}),
    ({"action": "mouse_move", "coordinate": [120, 240]},
     {"tool": "AC_set_mouse_position", "input": {"x": 120, "y": 240}}),
    ({"action": "type", "text": "hello world"},
     {"tool": "AC_write", "input": {"write_string": "hello world"}}),
    ({"action": "wait", "duration": 2.5},
     {"tool": "AC_sleep", "input": {"seconds": 2.5}}),
])
def test_simple_action_translations(payload, expected):
    assert _decision_from_computer_action(payload) == expected


def test_left_click_with_coordinate():
    out = _decision_from_computer_action({
        "action": "left_click", "coordinate": [50, 60],
    })
    assert out["tool"] == "AC_click_mouse"
    assert out["input"]["mouse_keycode"] == "mouse_left"
    assert (out["input"]["x"], out["input"]["y"]) == (50, 60)
    assert out["input"]["repeat"] == 1


def test_double_and_triple_click_repeat():
    dbl = _decision_from_computer_action({
        "action": "double_click", "coordinate": [1, 2],
    })
    tri = _decision_from_computer_action({
        "action": "triple_click", "coordinate": [3, 4],
    })
    assert dbl["input"]["repeat"] == 2
    assert tri["input"]["repeat"] == 3


def test_left_click_without_coordinate_uses_current_cursor():
    out = _decision_from_computer_action({"action": "left_click"})
    assert out["tool"] == "AC_click_mouse"
    assert "x" not in out["input"] and "y" not in out["input"]


def test_drag_requires_both_endpoints():
    with pytest.raises(AgentBackendError, match="start_coordinate"):
        _decision_from_computer_action({"action": "left_click_drag"})


def test_drag_translates_to_AC_drag():  # NOSONAR python:S1542  # reason: name mirrors the AC_drag executor command under test
    out = _decision_from_computer_action({
        "action": "left_click_drag",
        "start_coordinate": [0, 0],
        "end_coordinate": [100, 200],
    })
    assert out["tool"] == "AC_drag"
    assert out["input"]["start_x"] == 0
    assert out["input"]["end_x"] == 100
    assert out["input"]["end_y"] == 200


def test_scroll_translates_direction_to_sign():
    up = _decision_from_computer_action({
        "action": "scroll", "scroll_direction": "up", "scroll_amount": 5,
    })
    down = _decision_from_computer_action({
        "action": "scroll", "scroll_direction": "down", "scroll_amount": 5,
    })
    assert up["input"]["scroll_value"] == 5
    assert down["input"]["scroll_value"] == -5


def test_single_key_goes_through_type_keyboard():
    out = _decision_from_computer_action({"action": "key", "text": "Return"})
    assert out == {"tool": "AC_type_keyboard", "input": {"keycode": "enter"}}


def test_key_combo_goes_through_hotkey():
    out = _decision_from_computer_action({
        "action": "key", "text": "ctrl+shift+t",
    })
    assert out["tool"] == "AC_hotkey"
    assert out["input"]["key_code_list"] == ["ctrl", "shift", "t"]


def test_unknown_action_rejected():
    with pytest.raises(AgentBackendError, match="not recognised"):
        _decision_from_computer_action({"action": "frobnicate"})


def test_bad_coordinate_rejected():
    with pytest.raises(AgentBackendError, match="coordinate"):
        _decision_from_computer_action({
            "action": "mouse_move", "coordinate": [1],
        })


# --- xdotool key alias normalisation --------------------------------

@pytest.mark.parametrize("xdotool,expected", [
    ("Return", ["enter"]),
    ("escape", ["esc"]),
    ("ctrl_l+c", ["ctrl", "c"]),
    ("super_l+L", ["win", "l"]),
])
def test_parse_combo_normalises_xdotool_aliases(xdotool, expected):
    assert _parse_combo(xdotool) == expected


# --- end-to-end backend exercise ------------------------------------

def test_backend_emits_correct_tool_schema():
    client = _StubClient()
    backend = _backend(client=client)
    client.messages.queue(_StubResponse([
        _StubBlock(type="text", text="done"),
    ]))
    decision = backend.decide_next_action("goal", screenshot=b"png", history=[])
    # No tool_use → stop.
    assert decision == {"stop": True, "message": "done"}
    call = client.messages.calls[0]
    tools = call["tools"]
    assert len(tools) == 1
    assert tools[0]["type"] == "computer_20250124"
    assert tools[0]["name"] == "computer"
    assert tools[0]["display_width_px"] == 1920
    assert tools[0]["display_height_px"] == 1080


def test_backend_handles_tool_use_then_threads_result():
    client = _StubClient()
    backend = _backend(client=client)
    # First call → tool_use(screenshot)
    client.messages.queue(_StubResponse([
        _StubBlock(type="tool_use", id="tu_1", name="computer",
                   input={"action": "screenshot"}),
    ]))
    decision1 = backend.decide_next_action("goal", screenshot=b"png", history=[])
    assert decision1["tool"] == "AC_screenshot"

    # Second call → text → stop. History contains the prior screenshot step.
    history = [AgentStep(index=0, tool="AC_screenshot",
                         arguments={}, result=b"png_payload")]
    client.messages.queue(_StubResponse([
        _StubBlock(type="text", text="finished"),
    ]))
    decision2 = backend.decide_next_action(
        "goal", screenshot=b"png2", history=history,
    )
    assert decision2 == {"stop": True, "message": "finished"}
    # The second call must have included a tool_result block keyed to tu_1.
    second_msgs = client.messages.calls[1]["messages"]
    tool_results = [
        b for msg in second_msgs if msg["role"] == "user"
        for b in (msg["content"] if isinstance(msg["content"], list) else [])
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]
    assert tool_results, "tool_result should be threaded back"
    assert tool_results[0]["tool_use_id"] == "tu_1"
    # Screenshot tool result must carry an image block, not just text.
    assert any(c.get("type") == "image"
               for c in tool_results[0]["content"])


def test_backend_rewraps_client_failures_as_AgentBackendError():  # NOSONAR python:S1542  # reason: name mirrors the AgentBackendError class under test
    class _BoomClient:
        class messages:
            @staticmethod
            def create(**_):
                raise RuntimeError("network down")
    backend = ComputerUseAgentBackend(
        display_width_px=800, display_height_px=600,
        client=_BoomClient(),
    )
    with pytest.raises(AgentBackendError, match="network down"):
        backend.decide_next_action("goal", screenshot=None, history=[])


def test_backend_rejects_zero_display_size():
    with pytest.raises(AgentBackendError, match="display_width_px"):
        ComputerUseAgentBackend(
            display_width_px=0, display_height_px=600, client=_StubClient(),
        )


def test_error_in_history_becomes_text_tool_result():
    client = _StubClient()
    backend = _backend(client=client)
    client.messages.queue(_StubResponse([
        _StubBlock(type="tool_use", id="tu_x", name="computer",
                   input={"action": "left_click", "coordinate": [10, 10]}),
    ]))
    backend.decide_next_action("goal", screenshot=b"png", history=[])
    client.messages.queue(_StubResponse([
        _StubBlock(type="text", text="oops, stopping"),
    ]))
    history = [AgentStep(
        index=0, tool="AC_click_mouse",
        arguments={"x": 10, "y": 10},
        result=None, error="ValueError: bad target",
    )]
    backend.decide_next_action("goal", screenshot=b"png2", history=history)
    second_msgs = client.messages.calls[1]["messages"]
    tool_results = [
        b for msg in second_msgs if msg["role"] == "user"
        for b in (msg["content"] if isinstance(msg["content"], list) else [])
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]
    assert tool_results[0]["is_error"] is True
    assert tool_results[0]["content"][0]["type"] == "text"
    assert "bad target" in tool_results[0]["content"][0]["text"]
