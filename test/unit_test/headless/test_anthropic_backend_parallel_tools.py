"""The Anthropic agent backend must not allow parallel tool use.

This backend implements a strict one-tool-per-step loop: _handle_response
returns only the *first* tool_use block, and _ingest_history answers with
exactly one tool_result. The Messages API enables parallel tool use by default
and requires every tool_use block to be answered — so a response carrying two
tool_use blocks left one unanswered and the *next* request 400'd, ending the
run.
"""
from types import SimpleNamespace

from je_auto_control.utils.agent.backends.anthropic import AnthropicAgentBackend


class _RecordingClient:
    """Captures the kwargs the backend sends to messages.create."""

    def __init__(self, blocks):
        self.captured: dict = {}
        outer = self

        class _Messages:
            def create(self, **kwargs):
                outer.captured = kwargs
                return SimpleNamespace(content=blocks)

        self.messages = _Messages()


def _tool_use(block_id, name="click"):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input={})


def _backend(client):
    return AnthropicAgentBackend(client=client, tools=[{"name": "click"}])


def test_parallel_tool_use_is_disabled_on_every_request():
    """Regression: tool_choice was omitted, so parallel tool use stayed on."""
    client = _RecordingClient([_tool_use("toolu_A")])
    _backend(client).decide_next_action("goal", None, [])

    tool_choice = client.captured.get("tool_choice")
    assert tool_choice is not None, "tool_choice was not sent at all"
    assert tool_choice.get("disable_parallel_tool_use") is True
    # "auto" keeps the model free to answer without a tool — only the
    # parallelism is constrained.
    assert tool_choice.get("type") == "auto"


def test_the_rest_of_the_request_is_unchanged():
    """The fix must not disturb the other request fields."""
    client = _RecordingClient([_tool_use("toolu_A")])
    backend = _backend(client)
    backend.decide_next_action("find the button", None, [])

    assert client.captured["tools"] == [{"name": "click"}]
    assert client.captured["messages"]
    assert client.captured["max_tokens"]


def test_only_the_first_tool_use_is_returned():
    """Pins the loop's one-tool-per-step contract.

    This is *why* parallel tool use must be off: if the API ever returns two
    tool_use blocks, the backend answers only the first — so the second is left
    unanswered and the next request is rejected.
    """
    client = _RecordingClient([_tool_use("toolu_A"), _tool_use("toolu_B")])
    action = _backend(client).decide_next_action("goal", None, [])

    assert action["_tool_use_id"] == "toolu_A"
