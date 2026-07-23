"""Round-3 regressions for the OpenAI agent backend.

Covers:
  * ``parallel_tool_calls=False`` must be sent (the loop answers only the first
    tool_call, so parallel calls would 400 the next request),
  * a ``finish_reason == "length"`` truncation with no tool_call must be
    surfaced as an error rather than a successful final answer.
"""
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent.backends.base import AgentBackendError
from je_auto_control.utils.agent.backends.openai import OpenAIAgentBackend


class _RecordingOpenAIClient:
    """Captures chat.completions.create kwargs, returns a canned response."""

    def __init__(self, response):
        self.captured: dict = {}
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.captured = kwargs
                return response

        class _Chat:
            def __init__(self):
                self.completions = _Completions()

        self.chat = _Chat()


def _tool_call(call_id, name="AC_click_mouse", arguments="{}"):
    return SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments=arguments),
    )


def _response(tool_calls=None, content=None, finish_reason="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _backend(client):
    return OpenAIAgentBackend(client=client, tools=[{"type": "function"}])


def test_parallel_tool_calls_disabled_on_every_request():
    client = _RecordingOpenAIClient(
        _response(tool_calls=[_tool_call("call_1")], finish_reason="tool_calls"),
    )
    _backend(client).decide_next_action("goal", None, [])
    assert client.captured.get("parallel_tool_calls") is False


def test_length_truncation_without_tool_call_raises():
    client = _RecordingOpenAIClient(
        _response(content="partial", finish_reason="length"),
    )
    with pytest.raises(AgentBackendError):
        _backend(client).decide_next_action("goal", None, [])


def test_normal_completion_still_stops():
    client = _RecordingOpenAIClient(
        _response(content="done", finish_reason="stop"),
    )
    decision = _backend(client).decide_next_action("goal", None, [])
    assert decision == {"stop": True, "message": "done"}
