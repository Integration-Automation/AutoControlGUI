"""The Anthropic agent backends never rewrite a turn they have already sent.

Every step used to replace the older screenshots of the replayed conversation
with a text note. That edits messages the API has already seen: the prompt
cache misses on every step, and on models whose thinking blocks are bound to
the conversation before them the request is refused with HTTP 400. The
backends now leave sent turns alone and, once the screenshots pass the limit,
open a new history made of one summary message and the current screenshot.

Fake clients only: nothing here reaches the network.
"""
from __future__ import annotations

import copy
import io
import json
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from je_auto_control.utils.agent.agent_loop import AgentStep
from je_auto_control.utils.agent.backends import base
from je_auto_control.utils.agent.backends._computer_toolset import TOOLSET_TYPE
from je_auto_control.utils.agent.backends.anthropic import AnthropicAgentBackend
from je_auto_control.utils.agent.backends.anthropic_computer_use import (
    ComputerUseAgentBackend,
)

GOAL = "open the settings page"


def _png() -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _plain(value: Any) -> Any:
    """The JSON-shaped form of a message tree holding SDK-like objects."""
    if isinstance(value, SimpleNamespace):
        return {key: _plain(item) for key, item in vars(value).items()}
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


class _Client:
    """Stands in for the SDK client; snapshots each request as it was sent."""

    def __init__(self, reply) -> None:
        self._reply = reply
        self.sent: List[List[Dict[str, Any]]] = []
        self.live: List[List[Dict[str, Any]]] = []
        self.requests: List[Dict[str, Any]] = []
        self.messages = self
        self.beta = SimpleNamespace(messages=self)

    def create(self, **kwargs):
        self.requests.append(kwargs)
        self.live.append(kwargs["messages"])
        self.sent.append(copy.deepcopy(_plain(kwargs["messages"])))
        return self._reply(len(self.sent))


def _thinking() -> SimpleNamespace:
    return SimpleNamespace(type="thinking", thinking="", signature="sig")


def _reply(name: str, tool_input_for):
    def reply(number: int) -> SimpleNamespace:
        return SimpleNamespace(stop_reason="tool_use", content=[
            _thinking(),
            SimpleNamespace(type="tool_use", id=f"tu{number}", name=name,
                            input=tool_input_for(number)),
        ])
    return reply


def _drive(backend, steps: int, tool: str = "AC_screenshot") -> List[AgentStep]:
    history: List[AgentStep] = []
    for index in range(steps):
        decision = backend.decide_next_action(GOAL, _png(), history)
        history.append(AgentStep(index=index, tool=decision["tool"],
                                 arguments=decision["input"], result=f"result-{index}"))
    return history


def _ac_backend(client) -> AnthropicAgentBackend:
    tools = [{"name": "AC_click_mouse", "input_schema": {"type": "object"}}]
    return AnthropicAgentBackend(tools=tools, client=client)


def _ac_client() -> _Client:
    return _Client(_reply("AC_click_mouse", lambda number: {"x": number, "y": 2}))


def _beta_backend(client) -> ComputerUseAgentBackend:
    return ComputerUseAgentBackend(display_width_px=64, display_height_px=48,
                                   client=client, model="claude-opus-5")


def _toolset_backend(client) -> ComputerUseAgentBackend:
    return ComputerUseAgentBackend(display_width_px=64, display_height_px=48,
                                   client=client, model="claude-opus-5",
                                   tool_type=TOOLSET_TYPE)


def _cu_client(toolset: bool) -> _Client:
    if toolset:
        return _Client(_reply("screenshot", lambda number: {}))
    return _Client(_reply("computer", lambda number: {"action": "screenshot"}))


_PATHS = [
    pytest.param(_ac_backend, _ac_client, id="ac-tools"),
    pytest.param(_beta_backend, lambda: _cu_client(False), id="computer-beta"),
    pytest.param(_toolset_backend, lambda: _cu_client(True), id="computer-toolset"),
]


def _images(messages) -> int:
    return base.count_screenshots(messages)


def _blocks(messages, block_type: str) -> List[Dict[str, Any]]:
    return [block for message in messages for block in message["content"]
            if isinstance(block, dict) and block.get("type") == block_type]


@pytest.mark.parametrize("make_backend, make_client", _PATHS)
def test_sent_turns_are_never_mutated(make_backend, make_client):
    client = make_client()
    _drive(make_backend(client), base.SCREENSHOTS_KEPT * 3 + 2)
    # What each request held when it left is what its message list holds now.
    for sent, live in zip(client.sent, client.live):
        assert _plain(live)[:len(sent)] == sent
    # A request either extends the previous one byte for byte or starts over.
    restarts = 0
    for previous, current in zip(client.sent, client.sent[1:]):
        if current[:len(previous)] == previous:
            continue
        restarts += 1
        assert len(current) == 1
    assert restarts >= 1
    assert not any("omitted" in json.dumps(sent) for sent in client.sent)


@pytest.mark.parametrize("make_backend, make_client", _PATHS)
def test_compaction_opens_new_history(make_backend, make_client):
    client = make_client()
    _drive(make_backend(client), base.SCREENSHOTS_KEPT * 3 + 2)
    assert all(_images(sent) <= base.SCREENSHOTS_KEPT for sent in client.sent)
    restarted = [(number, sent) for number, sent in enumerate(client.sent)
                 if number and len(sent) == 1]
    assert restarted
    for number, sent in restarted:
        first = sent[0]
        assert first["role"] == "user"
        # No orphan tool_result, and no thinking block from the old conversation.
        assert [block["type"] for block in first["content"]] == ["image", "text"]
        text = first["content"][1]["text"]
        assert GOAL in text
        # Every action executed before this request is in the summary.
        for index in range(number):
            assert f"result-{index}" in text
    for sent in client.sent:
        answered = {block["tool_use_id"] for block in _blocks(sent, "tool_result")}
        asked = {block["id"] for block in _blocks(sent, "tool_use")}
        assert answered <= asked
        assert sent[0]["role"] == "user"


def test_compact_history_leaves_the_old_history_alone():
    old = [{"role": "user", "content": [{"type": "text", "text": "go"}]},
           {"role": "assistant", "content": [_thinking()]}]
    before = copy.deepcopy(_plain(old))
    image = {"type": "image", "source": {"type": "base64", "data": "abc"}}
    new = base.compact_history(old, "the summary", image)
    assert _plain(old) == before
    assert new == [{"role": "user", "content": [image, {"type": "text", "text": "the summary"}]}]
    assert base.compact_history(old, "s", None) == [
        {"role": "user", "content": [{"type": "text", "text": "s"}]}]


def test_summary_names_the_goal_and_bounds_each_action():
    steps = [
        AgentStep(index=0, tool="AC_click_mouse", arguments={"x": 1, "y": 2}, result="x" * 5000),
        AgentStep(index=1, tool="AC_write", arguments={"write_string": "hi"},
                  error="ValueError: boom"),
        AgentStep(index=2, tool=None, arguments=None, stop_reason="done"),
    ]
    summary = base.summarise_steps(GOAL, steps)
    assert GOAL in summary
    assert "AC_click_mouse" in summary
    assert '"x": 1' in summary
    assert "error: ValueError: boom" in summary
    assert len(summary) < 2000
    many = [AgentStep(index=i, tool="AC_press_key", arguments={"key": "a"}) for i in range(500)]
    assert len(base.summarise_steps(GOAL, many)) < 40_000
    assert "earlier actions" in base.summarise_steps(GOAL, many)


def test_a_history_over_the_byte_budget_is_compacted_too():
    image = {"type": "image", "source": {"type": "base64", "data": "a" * 600}}
    messages = [{"role": "user", "content": [image]}]
    assert not base.needs_compaction(messages, [image])
    assert base.needs_compaction(messages, [image], max_image_chars=1000)
    nested = [{"type": "tool_result", "tool_use_id": "t", "content": [image]}]
    assert base.needs_compaction(messages, nested, keep=1)
    assert not base.needs_compaction(messages, [{"type": "text", "text": "hi"}], keep=1)


def test_default_agent_tools_are_unchanged():
    from je_auto_control.utils.executor import action_executor
    assert action_executor._DEFAULT_AGENT_TOOLSET == [
        "AC_screenshot", "AC_screen_size", "AC_set_mouse_position",
        "AC_get_mouse_position", "AC_click_mouse", "AC_mouse_scroll", "AC_drag",
        "AC_write", "AC_type_keyboard", "AC_hotkey", "AC_press_key",
        "AC_locate_image_center", "AC_click_text", "AC_wait_text", "AC_wait_image",
        "AC_a11y_find", "AC_a11y_click", "AC_list_windows", "AC_focus_window",
        "AC_assert_text",
    ]


def test_the_openai_backend_still_prunes_in_place():
    from je_auto_control.utils.agent.backends import openai
    import inspect
    assert "prune_old_screenshots(self._messages)" in inspect.getsource(openai)
