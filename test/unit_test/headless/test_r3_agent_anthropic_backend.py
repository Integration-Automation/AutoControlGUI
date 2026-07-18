"""Round-3 regression: the Anthropic agent backend must not read a truncated
(max_tokens / refusal) turn as a successful final answer."""
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent.backends.anthropic import AnthropicAgentBackend
from je_auto_control.utils.agent.backends.base import AgentBackendError


class _Client:
    def __init__(self, content, stop_reason=None):
        blocks, reason = content, stop_reason

        class _Messages:
            def create(self, **kwargs):
                return SimpleNamespace(content=blocks, stop_reason=reason)

        self.messages = _Messages()


def _backend(client):
    return AnthropicAgentBackend(client=client, tools=[{"name": "click"}])


def test_max_tokens_truncation_without_tool_use_raises():
    client = _Client(
        [SimpleNamespace(type="text", text="cut off")], stop_reason="max_tokens",
    )
    with pytest.raises(AgentBackendError):
        _backend(client).decide_next_action("goal", None, [])


def test_refusal_without_tool_use_raises():
    client = _Client(
        [SimpleNamespace(type="text", text="")], stop_reason="refusal",
    )
    with pytest.raises(AgentBackendError):
        _backend(client).decide_next_action("goal", None, [])


def test_end_turn_final_answer_still_stops():
    client = _Client(
        [SimpleNamespace(type="text", text="all done")], stop_reason="end_turn",
    )
    decision = _backend(client).decide_next_action("goal", None, [])
    assert decision["stop"] is True
    assert decision["message"] == "all done"
