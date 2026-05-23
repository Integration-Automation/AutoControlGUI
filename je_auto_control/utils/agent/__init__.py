"""Phase 7.9: closed-loop Computer-Use Agent.

Given a natural-language goal, the agent drives the screen by alternating
between:

  1. **Observe** — take a screenshot of the current state.
  2. **Plan**    — feed the screenshot + goal + conversation history to a
                  vision-capable LLM, ask it which AC_* tool to call next.
  3. **Act**     — dispatch the model's chosen tool through
                  :mod:`tool_use_schema.run_tool_call`.
  4. **Verify**  — check the post-action screen (optional VLM diff) and
                  hand the result back to the model.
  5. **Loop**    — until the model returns ``stop`` / a final answer or
                  a budget exhausts (steps, wall clock, or token spend).

The default LLM backend is pluggable — see
:class:`agent_loop.AgentBackend`. The bundled fake backend lets the
test suite drive deterministic flows without touching a real API.
"""
from je_auto_control.utils.agent.agent_loop import (
    AgentBackend, AgentBudget, AgentLoop, AgentResult, AgentStep,
    FakeAgentBackend, run_agent,
)
from je_auto_control.utils.agent.backends import (
    AgentBackendError, AnthropicAgentBackend, OpenAIAgentBackend,
)

__all__ = [
    "AgentBackend", "AgentBudget", "AgentLoop", "AgentResult",
    "AgentStep", "FakeAgentBackend", "run_agent",
    "AnthropicAgentBackend", "OpenAIAgentBackend", "AgentBackendError",
]
