"""Phase 9.5: tests for Anthropic + OpenAI agent backends.

We don't make real API calls — both backends accept a pre-built
``client`` parameter that the tests fill with a stub. That lets us
verify the request shape, the tool-result threading, and the
response parsing without touching the network.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from je_auto_control.utils.agent import (
    AgentBackendError, AgentStep, AnthropicAgentBackend, OpenAIAgentBackend,
)
from je_auto_control.utils.agent.backends.base import (
    build_default_system_prompt, encode_screenshot_b64,
)


# --- shared helpers --------------------------------------------------

_FAKE_TOOLS = [
    {"name": "AC_click_mouse",
     "description": "Click the mouse.",
     "input_schema": {"type": "object", "properties": {}}},
]
_OPENAI_FAKE_TOOLS = [
    {"type": "function", "function": {
        "name": "AC_click_mouse",
        "description": "Click the mouse.",
        "parameters": {"type": "object", "properties": {}},
    }},
]


def test_encode_screenshot_b64_handles_none_and_bytes():
    assert encode_screenshot_b64(None) is None
    encoded = encode_screenshot_b64(b"\x89PNG\r\n\x1a\n")
    assert isinstance(encoded, str) and len(encoded) > 0


def test_default_system_prompt_includes_goal():
    out = build_default_system_prompt("open notepad")
    assert "open notepad" in out
    assert "AC_" in out


# --- AnthropicAgentBackend -----------------------------------------

class _FakeAnthropicClient:
    """Stub that returns a scripted .messages.create response."""

    def __init__(self, response) -> None:
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)
        self._response = response

    def _create(self, **kwargs):
        # Snapshot ``messages`` so later mutations on the live
        # conversation list don't rewrite history.
        snapshot = dict(kwargs)
        if "messages" in snapshot:
            snapshot["messages"] = [
                {**m, "content": list(m["content"])} if isinstance(m.get("content"), list) else dict(m)
                for m in snapshot["messages"]
            ]
        self.calls.append(snapshot)
        return self._response


def _anthropic_response_with_tool(tool_name="AC_click_mouse",
                                  tool_input=None, tool_id="tu-1"):
    return SimpleNamespace(content=[
        {"type": "tool_use", "name": tool_name,
         "input": tool_input or {}, "id": tool_id},
    ])


def _anthropic_response_with_text(text="all done"):
    return SimpleNamespace(content=[
        {"type": "text", "text": text},
    ])


def test_anthropic_returns_tool_use_decision():
    client = _FakeAnthropicClient(_anthropic_response_with_tool())
    backend = AnthropicAgentBackend(tools=_FAKE_TOOLS, client=client)
    decision = backend.decide_next_action(
        goal="click", screenshot=b"png", history=[],
    )
    assert decision["tool"] == "AC_click_mouse"
    assert decision["input"] == {}
    # The client should have received the rendered tool list verbatim.
    assert client.calls[0]["tools"] == _FAKE_TOOLS


def test_anthropic_returns_stop_on_text_only_response():
    client = _FakeAnthropicClient(_anthropic_response_with_text("done!"))
    backend = AnthropicAgentBackend(tools=_FAKE_TOOLS, client=client)
    decision = backend.decide_next_action(
        goal="x", screenshot=None, history=[],
    )
    assert decision.get("stop") is True
    assert decision.get("message") == "done!"


def test_anthropic_threads_tool_result_back_on_next_turn():
    client = _FakeAnthropicClient(_anthropic_response_with_tool())
    backend = AnthropicAgentBackend(tools=_FAKE_TOOLS, client=client)
    # Turn 1: model picks a tool.
    backend.decide_next_action(goal="g", screenshot=None, history=[])
    # Turn 2: feed back the tool result via history.
    client._response = _anthropic_response_with_text("ok")
    backend.decide_next_action(
        goal="g", screenshot=None,
        history=[AgentStep(
            index=0, tool="AC_click_mouse",
            arguments={}, result={"clicked": True},
        )],
    )
    # The most recent ``messages`` arg should contain a tool_result block.
    last_call = client.calls[-1]["messages"]
    assert any(
        isinstance(m.get("content"), list)
        and any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in m["content"]
        )
        for m in last_call
    ), "expected a tool_result block on the second turn"


def test_anthropic_screenshot_attached_when_present():
    client = _FakeAnthropicClient(_anthropic_response_with_tool())
    backend = AnthropicAgentBackend(tools=_FAKE_TOOLS, client=client)
    backend.decide_next_action(goal="g", screenshot=b"\x89PNG", history=[])
    # The user message should contain an image block.
    user_msg = client.calls[0]["messages"][-1]
    types = {b.get("type") for b in user_msg["content"]}
    assert "image" in types
    assert "text" in types


def test_anthropic_requires_tools_list():
    with pytest.raises(AgentBackendError, match="non-empty"):
        AnthropicAgentBackend(tools=[])


def test_anthropic_raises_when_sdk_missing():
    # No client + sdk import failure → AgentBackendError.
    backend = AnthropicAgentBackend(tools=_FAKE_TOOLS, client=None)
    backend._client = None
    # Patch the import to raise.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        with pytest.raises(AgentBackendError, match="anthropic SDK"):
            backend._resolve_client()
    finally:
        builtins.__import__ = real_import


def test_anthropic_wraps_sdk_failures():
    class _Boom:
        messages = SimpleNamespace(
            create=MagicMock(side_effect=RuntimeError("rate limited")),
        )

    backend = AnthropicAgentBackend(tools=_FAKE_TOOLS, client=_Boom())
    with pytest.raises(AgentBackendError, match="anthropic"):
        backend.decide_next_action(goal="g", screenshot=None, history=[])


# --- OpenAIAgentBackend --------------------------------------------

def _openai_tool_call(name="AC_click_mouse",
                     args="{}", call_id="call_1"):
    return SimpleNamespace(
        id=call_id, type="function",
        function=SimpleNamespace(name=name, arguments=args),
    )


def _openai_response(tool_calls=None, text=""):
    msg = SimpleNamespace(
        content=text or None,
        tool_calls=tool_calls or [],
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FakeOpenAIClient:
    def __init__(self, response) -> None:
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )
        self._response = response

    def _create(self, **kwargs):
        snapshot = dict(kwargs)
        if "messages" in snapshot:
            snapshot["messages"] = [
                {**m, "content": list(m["content"])} if isinstance(m.get("content"), list) else dict(m)
                for m in snapshot["messages"]
            ]
        self.calls.append(snapshot)
        return self._response


def test_openai_returns_tool_call_decision():
    response = _openai_response(tool_calls=[
        _openai_tool_call(args='{"button": "left"}'),
    ])
    client = _FakeOpenAIClient(response)
    backend = OpenAIAgentBackend(tools=_OPENAI_FAKE_TOOLS, client=client)
    decision = backend.decide_next_action(
        goal="click", screenshot=None, history=[],
    )
    assert decision["tool"] == "AC_click_mouse"
    assert decision["input"] == {"button": "left"}


def test_openai_returns_stop_when_no_tool_call():
    response = _openai_response(text="all done")
    client = _FakeOpenAIClient(response)
    backend = OpenAIAgentBackend(tools=_OPENAI_FAKE_TOOLS, client=client)
    decision = backend.decide_next_action(
        goal="g", screenshot=None, history=[],
    )
    assert decision.get("stop") is True
    assert decision.get("message") == "all done"


def test_openai_handles_malformed_tool_arguments():
    response = _openai_response(tool_calls=[
        _openai_tool_call(args="not-json-at-all"),
    ])
    client = _FakeOpenAIClient(response)
    backend = OpenAIAgentBackend(tools=_OPENAI_FAKE_TOOLS, client=client)
    decision = backend.decide_next_action(
        goal="g", screenshot=None, history=[],
    )
    # Malformed args fall back to an empty dict instead of crashing.
    assert decision["input"] == {}


def test_openai_threads_tool_result_via_history():
    """The next-turn ``messages`` payload includes a ``role: tool`` entry."""
    first = _openai_response(tool_calls=[_openai_tool_call(call_id="c1")])
    client = _FakeOpenAIClient(first)
    backend = OpenAIAgentBackend(tools=_OPENAI_FAKE_TOOLS, client=client)
    backend.decide_next_action(goal="g", screenshot=None, history=[])
    # Now feed the tool result via history.
    client._response = _openai_response(text="done")
    backend.decide_next_action(
        goal="g", screenshot=None,
        history=[AgentStep(
            index=0, tool="AC_click_mouse",
            arguments={}, result={"ok": True},
        )],
    )
    msgs = client.calls[-1]["messages"]
    tool_messages = [m for m in msgs if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "c1"


def test_openai_attaches_screenshot_as_image_url():
    response = _openai_response(tool_calls=[_openai_tool_call()])
    client = _FakeOpenAIClient(response)
    backend = OpenAIAgentBackend(tools=_OPENAI_FAKE_TOOLS, client=client)
    backend.decide_next_action(
        goal="g", screenshot=b"\x89PNG\r\n", history=[],
    )
    user_msg = client.calls[0]["messages"][-1]
    types = {b["type"] for b in user_msg["content"]}
    assert "image_url" in types


def test_openai_requires_tools_list():
    with pytest.raises(AgentBackendError):
        OpenAIAgentBackend(tools=[])


def test_openai_raises_when_sdk_missing():
    backend = OpenAIAgentBackend(tools=_OPENAI_FAKE_TOOLS, client=None)
    backend._client = None
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        with pytest.raises(AgentBackendError, match="openai SDK"):
            backend._resolve_client()
    finally:
        builtins.__import__ = real_import
