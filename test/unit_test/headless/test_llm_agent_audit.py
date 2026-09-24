"""LLM / agent / VLM defects from the 2026-09-24 audit (fake clients only).

Agent requests had no timeout (the SDK default is 600 s per attempt, retried)
and resent every screenshot of the run, which outgrows the request size limit
within the default step budget; ``only=[]`` exported every command; an empty
plan reached the executor; and a VLM reply was parsed out of the middle of a
longer number and, with no region, clicked even when off the screenshot.
"""
import pytest

from je_auto_control.utils.agent.backends import base
from je_auto_control.utils.agent.backends.anthropic import AnthropicAgentBackend
from je_auto_control.utils.agent.backends.openai import OpenAIAgentBackend
from je_auto_control.utils.llm.backends.base import LLMBackend
from je_auto_control.utils.llm.planner import LLMPlanError, plan_actions
from je_auto_control.utils.tool_use_schema import (
    export_anthropic_tools, export_openai_tools,
)
from je_auto_control.utils.vision import vlm_api
from je_auto_control.utils.vision.backends._parse import parse_coords


def _image(tag):
    return {"type": "image", "source": {"type": "base64", "data": tag}}


def _texts(messages):
    return [block.get("text") for message in messages
            for block in message["content"] if block.get("type") == "text"]


def test_only_the_newest_screenshots_are_kept_including_nested_ones():
    messages = [
        {"role": "user", "content": [_image("a"), {"type": "text", "text": "go"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                      "content": [_image("b")]}]},
        {"role": "user", "content": [_image("c")]},
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "d"}}]},
    ]
    base.prune_old_screenshots(messages, keep=2)
    assert messages[0]["content"][0] == {"type": "text", "text": "[earlier screenshot omitted]"}
    assert messages[0]["content"][1]["text"] == "go"
    nested = messages[1]["content"][0]
    assert nested["tool_use_id"] == "t1"
    assert nested["content"][0]["type"] == "text"
    assert messages[2]["content"][0]["source"]["data"] == "c"
    assert messages[3]["content"][0]["type"] == "image_url"


class _Recorder:
    """Stands in for both SDK clients; records every create() call."""

    def __init__(self):
        self.calls = []
        self.messages = self
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        # The backends keep appending to the same list, so snapshot it.
        kwargs["image_count"] = sum(
            1 for message in kwargs["messages"]
            for block in (message.get("content") if isinstance(message.get("content"), list) else [])
            if isinstance(block, dict) and block.get("type") in ("image", "image_url"))
        self.calls.append(kwargs)
        raise RuntimeError("stop after recording")


@pytest.mark.parametrize("backend_cls, tools", [
    (AnthropicAgentBackend, [{"name": "AC_x", "input_schema": {}}]),
    (OpenAIAgentBackend, [{"type": "function", "function": {"name": "AC_x"}}]),
])
def test_agent_requests_carry_a_timeout_and_bounded_screenshots(backend_cls, tools):
    client = _Recorder()
    backend = backend_cls(tools=tools, client=client)
    for _ in range(base.SCREENSHOTS_KEPT + 4):
        with pytest.raises(base.AgentBackendError):
            backend.decide_next_action("goal", b"png", [])
    assert all(call["timeout"] == base.REQUEST_TIMEOUT_S for call in client.calls)
    assert client.calls[-1]["image_count"] == base.SCREENSHOTS_KEPT


def test_an_empty_only_list_exports_no_tools():
    assert export_anthropic_tools(only=[]) == []
    assert export_openai_tools(only=[]) == []
    assert export_anthropic_tools(only=None)


class _FixedLLM(LLMBackend):
    name = "fixed"
    available = True

    def __init__(self, reply):
        self._reply = reply

    def complete(self, prompt, system=None, model=None, max_tokens=1024):
        return self._reply


def test_an_empty_plan_is_refused():
    with pytest.raises(LLMPlanError, match="empty plan"):
        plan_actions("do nothing", backend=_FixedLLM("[]"), known_commands=["AC_x"])


@pytest.mark.parametrize("reply, expected", [
    ("123456, 7", None),
    ("1.5, 2", None),
    ("at 40, 60.", (40, 60)),
    ("-3, 8", (-3, 8)),
])
def test_coordinates_are_not_cut_out_of_longer_numbers(reply, expected):
    assert parse_coords(reply) == expected


def _png(width, height):
    return (bytes.fromhex("89504e470d0a1a0a") + b"\0\0\0\rIHDR"
            + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\0" * 8)


class _FixedVLM:
    available = True

    def __init__(self, coords):
        self._coords = coords

    def locate(self, image_bytes, description, model=None):
        return self._coords


@pytest.mark.parametrize("coords, expected", [
    ((5000, 10), None), ((10, -1), None), ((99, 49), (99, 49)),
])
def test_a_full_screen_reply_off_the_screenshot_is_not_a_location(monkeypatch, coords, expected):
    monkeypatch.setattr(vlm_api, "_capture_screenshot_bytes", lambda region=None: _png(100, 50))
    assert vlm_api.locate_by_description("ok button", backend=_FixedVLM(coords)) == expected
