"""Phase 9.5: production agent backends for the Computer-Use loop.

The Phase 7.9 :class:`AgentLoop` only shipped with ``FakeAgentBackend``
— enough for tests, useless in production. This package adds two real
backends that wrap Anthropic's Messages API and OpenAI's
Responses/Chat-Completions APIs with the tool-use schemas Phase 7.8
auto-generates from the executor.

Both backends share the same contract: given a goal, a screenshot,
and the conversation history, return ``{"tool": "...", "input": ...}``
to act or ``{"stop": True, "message": ...}`` to halt. The screenshot
is shipped as a PNG image attachment so the model can read the actual
pixels — that's the whole point of "computer use".

Neither vendor SDK is a hard dep. Each backend imports its SDK lazily
and raises a clear :class:`AgentBackendError` when the SDK is missing
or the API key isn't configured.
"""
from je_auto_control.utils.agent.backends.anthropic import (
    AnthropicAgentBackend,
)
from je_auto_control.utils.agent.backends.anthropic_computer_use import (
    ComputerUseAgentBackend,
)
from je_auto_control.utils.agent.backends.base import (
    AgentBackendError, build_default_system_prompt,
)
from je_auto_control.utils.agent.backends.openai import (
    OpenAIAgentBackend,
)

__all__ = [
    "AnthropicAgentBackend", "ComputerUseAgentBackend", "OpenAIAgentBackend",
    "AgentBackendError", "build_default_system_prompt",
]
