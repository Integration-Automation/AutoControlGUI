"""The LLM / VLM / agent layer at the edges the audit found (fake clients only, no API calls).

A turn cut short never runs its tool calls; tool schemas carry real types and
no private or callback parameters; numeric-string and scaled coordinates are
handled; the loop contains what the executor contains; VLM replies are read in
the pixels of the image the model saw, in more answer formats, and request
failures are errors; OpenAI refusals are not answers; a reused backend starts
fresh; model ids with prefixes and dates are priced.
"""
import io
import types

import pytest

from je_auto_control.utils.agent.agent_loop import AgentLoop, AgentStep, FakeAgentBackend
from je_auto_control.utils.agent.backends import base
from je_auto_control.utils.agent.backends._computer_toolset import fit_screenshot, image_tier, unscale_decision
from je_auto_control.utils.agent.backends.anthropic import AnthropicAgentBackend
from je_auto_control.utils.agent.backends.anthropic_computer_use import (
    ComputerUseAgentBackend, _clamp_decision, _parse_combo, _tool_result_content,
)
from je_auto_control.utils.agent.backends.openai import OpenAIAgentBackend


def _png(width, height):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _block(**fields):
    return types.SimpleNamespace(**fields)


class _Messages:
    def __init__(self, script):
        self.calls, self.script = [], list(script)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.script.pop(0)


class _Client:
    def __init__(self, script):
        self.messages = _Messages(script)
        self.beta = types.SimpleNamespace(messages=self.messages)


def _cut_short(stop_reason, tool_use):
    return types.SimpleNamespace(stop_reason=stop_reason, content=[tool_use])


# --- truncated turns ------------------------------------------------------------------------------

@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_a_generic_turn_cut_short_does_not_run_its_tool(stop_reason):
    tool_use = _block(type="tool_use", name="AC_click_mouse", id="t1", input={"mouse_keycode": "mouse_left"})
    backend = AnthropicAgentBackend(tools=[{"name": "AC_click_mouse", "input_schema": {}}],
                                    client=_Client([_cut_short(stop_reason, tool_use)]))
    with pytest.raises(base.AgentBackendError, match=stop_reason):
        backend.decide_next_action("goal", None, [])


@pytest.mark.parametrize("model, name, payload", [
    ("claude-opus-5", "computer", {"action": "type", "text": "rm -rf ~/pro"}),
    ("claude-opus-5-5", "left_click", {"coordinate": [5, 5]}),
])
def test_a_computer_use_turn_cut_short_does_not_run_its_tool(model, name, payload):
    tool_use = _block(type="tool_use", name=name, id="t1", input=payload)
    backend = ComputerUseAgentBackend(display_width_px=100, display_height_px=100, model=model,
                                      client=_Client([_cut_short("max_tokens", tool_use)]))
    with pytest.raises(base.AgentBackendError, match="max_tokens"):
        backend.decide_next_action("goal", _png(100, 100), [])


# --- tool schemas ---------------------------------------------------------------------------------

def test_tool_schemas_carry_real_types_and_no_private_or_callback_parameters():
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.tool_use_schema.schema import infer_parameters
    click, _ = infer_parameters(executor.event_dict["AC_click_mouse"])
    assert "integer" in click["x"]["type"]
    execute, _ = infer_parameters(executor.event_dict["AC_execute_action"])
    assert "_validated" not in execute and "step_callback" not in execute
    assert "action_list" in execute


# --- coordinates ----------------------------------------------------------------------------------

def test_numeric_string_coordinates_are_unscaled_and_malformed_actions_are_skipped():
    decision = unscale_decision({"tool": "AC_click_mouse", "input": {"x": "1400", "y": "800"}}, (0.5, 0.5))
    assert decision["input"] == {"x": 2800, "y": 1600}
    nested = {"tool": "AC_execute_action",
              "input": {"action_list": [{"a": 1}, [None], [5], ["AC_click_mouse", {"x": 10, "y": 10}]]}}
    unscale_decision(nested, (0.5, 0.5))
    _clamp_decision(nested, 100, 100)
    assert nested["input"]["action_list"][-1][1] == {"x": 20, "y": 20}


def test_the_cursor_position_is_given_in_screenshot_pixels():
    step = AgentStep(index=0, tool="AC_get_mouse_position", arguments={}, result=(2981, 1491))
    text = _tool_result_content(step, None, (0.5, 0.5))[0]["text"]
    assert text == "(1490, 746)"


def test_ctrl_plus_is_ctrl_and_the_plus_key():
    keys = _parse_combo("ctrl++")
    assert len(keys) == 2 and keys[0] != keys[1]


def test_scrolling_up_says_so():
    from je_auto_control.utils.agent.backends.anthropic_computer_use import _scroll_decision
    decision = _scroll_decision({"scroll_direction": "up", "scroll_amount": 3})
    assert decision["input"] == {"scroll_value": 3, "scroll_direction": "scroll_up"}


# --- the loop ---------------------------------------------------------------------------------------

def test_the_loop_contains_what_the_executor_contains():
    def runner(tool, args):
        raise KeyError(0)

    loop = AgentLoop(backend=FakeAgentBackend([{"tool": "AC_x", "input": {}}]),
                     tool_runner=runner, screenshot_fn=lambda: None)
    result = loop.run("goal")
    assert result.steps[0].error.startswith("KeyError")


# --- VLM --------------------------------------------------------------------------------------------

def test_a_vlm_reply_is_read_in_the_pixels_of_the_image_given():
    from je_auto_control.utils.vision.backends.anthropic_backend import AnthropicVLMBackend
    sent = []

    def create(**kwargs):
        sent.append(kwargs)
        return types.SimpleNamespace(content=[_block(type="text", text="728, 409")])

    backend = AnthropicVLMBackend.__new__(AnthropicVLMBackend)
    backend.available = True
    backend._client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))  # noqa: SLF001
    point = backend.locate(_png(1920, 1080), "the button", model="claude-sonnet-4-5")
    _fitted, (sx, sy) = fit_screenshot(_png(1920, 1080), image_tier("claude-sonnet-4-5"))
    assert sx < 1 and point == (round(728 / sx), round(409 / sy))


@pytest.mark.parametrize("reply, expected", [
    ("x=512, y=300", (512, 300)),
    ("x: 512, y: 300", (512, 300)),
    ('{"x": 512, "y": 300}', (512, 300)),
    ("512.4, 300.6", (512, 301)),
    ("at 40, 60.", (40, 60)),
])
def test_vlm_answers_in_common_formats_are_read(reply, expected):
    from je_auto_control.utils.vision.backends._parse import parse_coords
    assert parse_coords(reply) == expected


def test_an_openai_vlm_request_failure_is_an_error_not_not_found(monkeypatch):
    from je_auto_control.utils.vision.backends import openai_backend
    from je_auto_control.utils.vision.backends.base import VLMRequestError

    def reset(**_kwargs):
        raise ConnectionResetError("connection reset")

    backend = openai_backend.OpenAIVLMBackend.__new__(openai_backend.OpenAIVLMBackend)
    backend.available = True
    backend._client = types.SimpleNamespace(  # noqa: SLF001
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=reset)))
    with pytest.raises(VLMRequestError, match="reset"):
        backend.locate(b"png", "the button")


# --- OpenAI -----------------------------------------------------------------------------------------

def _choice(message=None, finish_reason="stop"):
    message = message or types.SimpleNamespace(content="done", tool_calls=None, refusal=None)
    return types.SimpleNamespace(message=message, finish_reason=finish_reason)


class _Completions:
    def __init__(self, response):
        self.response, self.calls = response, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _openai(response, tools=None):
    completions = _Completions(response)
    client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=completions))
    tools = tools or [{"type": "function", "function": {"name": "AC_x"}}]
    return OpenAIAgentBackend(tools=tools, client=client), completions


@pytest.mark.parametrize("response, match", [
    (types.SimpleNamespace(choices=[_choice(types.SimpleNamespace(content=None, tool_calls=None,
                                                                   refusal="I can't help"))]), "refused"),
    (types.SimpleNamespace(choices=[_choice(finish_reason="content_filter")]), "content filter"),
    (types.SimpleNamespace(choices=[]), "no choices"),
])
def test_openai_refusals_filtered_and_empty_replies_are_not_answers(response, match):
    backend, _ = _openai(response)
    with pytest.raises(base.AgentBackendError, match=match):
        backend.decide_next_action("goal", None, [])


def test_openai_refuses_more_tools_than_it_accepts():
    tools = [{"type": "function", "function": {"name": f"AC_{i}"}} for i in range(129)]
    with pytest.raises(base.AgentBackendError, match="128"):
        OpenAIAgentBackend(tools=tools, client=object())


def test_a_reused_backend_starts_each_run_afresh():
    backend, completions = _openai(types.SimpleNamespace(choices=[_choice()]))
    backend.decide_next_action("first goal", None, [])
    backend.decide_next_action("second goal", None, [])
    system = completions.calls[-1]["messages"][0]["content"]
    assert "second goal" in system and "first goal" not in system


# --- pricing ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("model", ["global.anthropic.claude-sonnet-4-5-20250929-v1:0", "gpt-4o-2024-08-06"])
def test_prefixed_and_dated_model_ids_are_priced(model):
    from je_auto_control.utils.cost_telemetry.pricing import estimate_usd
    assert estimate_usd(model, 1_000_000, 0) > 0
