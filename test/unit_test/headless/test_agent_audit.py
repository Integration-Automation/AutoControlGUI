"""Regression tests for the agent / VLM defects of the 2026-09-23 audit.

Computer-use translated most actions into calls the executor cannot make
(a ``repeat`` argument, ``AC_sleep`` / ``AC_drag`` outside ``event_dict``,
``AC_hold_key`` with the wrong keywords) -- the existing tests passed only
because they never ran a translation against the real commands. The agent
backends executed any tool name the model returned, OpenAI arguments that were
not a JSON object crashed the run, garbled coordinates escaped as ValueError,
and the VLM backends let provider errors out and clicked outside the region.
"""
import inspect
import sys
import types
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent.backends import anthropic_computer_use as cu
from je_auto_control.utils.agent.backends.anthropic import AnthropicAgentBackend
from je_auto_control.utils.agent.backends.base import AgentBackendError
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.executor.action_schema import validate_actions
from je_auto_control.utils.vision import vlm_api

_PAYLOADS = [
    {"action": "screenshot"},
    {"action": "cursor_position"},
    {"action": "mouse_move", "coordinate": [10, 20]},
    {"action": "type", "text": "hi"},
    {"action": "wait", "duration": 0.5},
    {"action": "left_click", "coordinate": [1, 2]},
    {"action": "right_click"},
    {"action": "middle_click", "coordinate": [1, 2]},
    {"action": "double_click", "coordinate": [1, 2]},
    {"action": "triple_click", "coordinate": [1, 2]},
    {"action": "left_click_drag", "start_coordinate": [0, 0], "end_coordinate": [5, 5]},
    {"action": "scroll", "scroll_direction": "up", "scroll_amount": 2},
    {"action": "key", "text": "ctrl+a"},
    {"action": "key", "text": "Return"},
    {"action": "hold_key", "text": "shift", "duration": 0.2},
    {"action": "left_mouse_down", "coordinate": [3, 4]},
    {"action": "left_mouse_up", "coordinate": [3, 4]},
]


@pytest.mark.parametrize("payload", _PAYLOADS, ids=lambda p: p["action"])
def test_every_translation_binds_to_a_real_command(payload):
    decision = cu._decision_from_computer_action(payload)
    command = executor.event_dict.get(decision["tool"])
    assert command is not None, f"{decision['tool']} is not a command the tool runner can call"
    inspect.signature(command).bind(**decision["input"])
    for action in decision["input"].get("action_list", []):
        validate_actions([action], executor.known_commands())
        inner = executor.event_dict.get(action[0])
        if inner is not None:  # block commands (AC_sleep) are validated above
            inspect.signature(inner).bind(**action[1])


def _computer_use(width=100, height=100):
    return cu.ComputerUseAgentBackend(display_width_px=width, display_height_px=height,
                                      client=object())


def _response(*blocks):
    return SimpleNamespace(content=list(blocks), stop_reason="tool_use")


def test_coordinates_are_clamped_to_the_display():
    decision = _computer_use()._handle_response(_response(
        {"type": "tool_use", "name": "computer", "id": "t1",
         "input": {"action": "left_click", "coordinate": [-500, 99999]}}))
    assert (decision["input"]["x"], decision["input"]["y"]) == (0, 99)


@pytest.mark.parametrize("coordinate", [["a", 1], [float("nan"), 1], [None, 1]])
def test_a_garbled_coordinate_is_a_backend_error(coordinate):
    with pytest.raises(AgentBackendError):
        cu._decision_from_computer_action({"action": "mouse_move", "coordinate": coordinate})


def test_computer_use_refuses_a_tool_it_did_not_offer():
    with pytest.raises(AgentBackendError, match="only 'computer'"):
        _computer_use()._handle_response(_response(
            {"type": "tool_use", "name": "AC_shell_command", "id": "t1", "input": {}}))


def test_the_messages_backend_refuses_a_tool_it_did_not_offer():
    backend = AnthropicAgentBackend(tools=[{"name": "AC_click_mouse"}], client=object())
    with pytest.raises(AgentBackendError, match="not offered"):
        backend._handle_response(_response(
            {"type": "tool_use", "name": "AC_shell_command", "id": "t1",
             "input": {"shell_command": "rm -rf somedir"}}))


@pytest.mark.parametrize("arguments", ["[1, 2]", '"x"', "not json"])
def test_openai_arguments_must_be_a_json_object(arguments):
    from je_auto_control.utils.agent.backends.openai import OpenAIAgentBackend
    backend = OpenAIAgentBackend(tools=[{"type": "function", "function": {"name": "AC_click_mouse"}}],
                                 client=object())
    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="AC_click_mouse", arguments=arguments))
    message = SimpleNamespace(tool_calls=[call], content=None, role="assistant")
    response = SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="tool_calls")])
    with pytest.raises(AgentBackendError):
        backend._handle_response(response)


class _FixedBackend:
    available = True

    def __init__(self, coords):
        self.coords = coords

    def locate(self, _image, _description, model=None):
        return self.coords


def test_a_vlm_point_outside_the_region_is_not_found(monkeypatch):
    monkeypatch.setattr(vlm_api, "_capture_screenshot_bytes", lambda region: b"png")
    region = [100, 100, 200, 200]
    assert vlm_api.locate_by_description("ok", screen_region=region,
                                         backend=_FixedBackend((-40, 5000))) is None
    assert vlm_api.locate_by_description("ok", screen_region=region,
                                         backend=_FixedBackend((10, 20))) == (110, 120)


def test_a_vlm_provider_error_is_contained(monkeypatch):
    fake_sdk = types.ModuleType("anthropic")

    class AnthropicError(Exception):
        pass

    class RateLimitError(AnthropicError):
        pass

    fake_sdk.AnthropicError = AnthropicError
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)
    from je_auto_control.utils.vision.backends.anthropic_backend import AnthropicVLMBackend

    def rate_limited(**_kwargs):
        raise RateLimitError("429")

    backend = AnthropicVLMBackend.__new__(AnthropicVLMBackend)
    backend.available = True
    backend._client = SimpleNamespace(messages=SimpleNamespace(create=rate_limited))
    assert backend.locate(b"png", "the button") is None


def test_backend_errors_are_in_the_framework_family():
    from je_auto_control.utils.llm.backends.base import LLMNotAvailableError
    from je_auto_control.utils.vision.backends.base import VLMNotAvailableError
    for error in (AgentBackendError, LLMNotAvailableError, VLMNotAvailableError):
        assert issubclass(error, AutoControlException) and issubclass(error, RuntimeError)
