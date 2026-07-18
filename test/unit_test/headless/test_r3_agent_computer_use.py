"""Round-3 regressions for the Anthropic Computer-Use agent backend.

Covers:
  * parallel tool use must be disabled on every request,
  * ``left_mouse_down`` / ``left_mouse_up`` must map to AC_* calls instead of
    aborting the run,
  * an explicit ``0`` duration / scroll amount must be honoured,
  * a truncated (max_tokens / refusal) turn with no tool_use must be surfaced
    as an error rather than a successful final answer.
"""
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent.backends.anthropic_computer_use import (
    ComputerUseAgentBackend, _action_wait, _decision_from_computer_action,
    _scroll_decision,
)
from je_auto_control.utils.agent.backends.base import AgentBackendError


class _RecordingClient:
    """Captures messages.create kwargs and returns a canned response."""

    def __init__(self, content, stop_reason=None):
        self.captured: dict = {}
        outer = self

        class _Messages:
            def create(self, **kwargs):
                outer.captured = kwargs
                return SimpleNamespace(content=content, stop_reason=stop_reason)

        self.messages = _Messages()


def _computer_tool_use(block_id, payload):
    return SimpleNamespace(
        type="tool_use", id=block_id, name="computer", input=payload,
    )


def _backend(client):
    return ComputerUseAgentBackend(
        display_width_px=1280, display_height_px=800, client=client,
    )


# --- finding 1a: tool_choice / disable_parallel_tool_use ---------------

def test_tool_choice_disables_parallel_tool_use():
    client = _RecordingClient(
        [_computer_tool_use("toolu_A", {"action": "screenshot"})],
    )
    _backend(client).decide_next_action("goal", None, [])

    tool_choice = client.captured.get("tool_choice")
    assert tool_choice is not None, "tool_choice was not sent at all"
    assert tool_choice.get("type") == "auto"
    assert tool_choice.get("disable_parallel_tool_use") is True


# --- finding 1b: press/release verbs must not abort the run ------------

def test_left_mouse_down_maps_to_press_mouse():
    decision = _decision_from_computer_action({"action": "left_mouse_down"})
    assert decision["tool"] == "AC_press_mouse"
    assert decision["input"]["mouse_keycode"] == "mouse_left"


def test_left_mouse_up_maps_to_release_mouse():
    decision = _decision_from_computer_action({"action": "left_mouse_up"})
    assert decision["tool"] == "AC_release_mouse"
    assert decision["input"]["mouse_keycode"] == "mouse_left"


def test_left_mouse_down_passes_coordinate_when_present():
    decision = _decision_from_computer_action(
        {"action": "left_mouse_down", "coordinate": [10, 20]},
    )
    assert decision["input"]["x"] == 10
    assert decision["input"]["y"] == 20


# --- finding 1c: an explicit 0 must be honoured ------------------------

def test_wait_honours_explicit_zero_duration():
    assert _action_wait({"duration": 0})["input"]["seconds"] == pytest.approx(0.0)


def test_wait_defaults_when_duration_absent():
    assert _action_wait({})["input"]["seconds"] == pytest.approx(1.0)


def test_scroll_honours_explicit_zero_amount():
    decision = _scroll_decision({"scroll_direction": "up", "scroll_amount": 0})
    assert decision["input"]["scroll_value"] == 0


def test_scroll_defaults_when_amount_absent():
    decision = _scroll_decision({"scroll_direction": "up"})
    assert decision["input"]["scroll_value"] == 3


# --- finding 3: truncation must not read as success --------------------

def test_max_tokens_truncation_without_tool_use_raises():
    client = _RecordingClient(
        [SimpleNamespace(type="text", text="partial plan")],
        stop_reason="max_tokens",
    )
    with pytest.raises(AgentBackendError):
        _backend(client).decide_next_action("goal", None, [])


def test_complete_final_answer_still_stops():
    client = _RecordingClient(
        [SimpleNamespace(type="text", text="done")],
        stop_reason="end_turn",
    )
    decision = _backend(client).decide_next_action("goal", None, [])
    assert decision == {"stop": True, "message": "done"}
