"""The beta ``computer`` tool path of the Anthropic computer-use backend.

``computer_20251124`` (and the older ``computer_20250124``): one tool named
``computer``, declared with a display size, sent under a beta, answering with
one ``tool_use`` per turn whose ``action`` field is the verb. The toolset
path is :mod:`._computer_toolset_path`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.agent.agent_loop import AgentStep
from je_auto_control.utils.agent.backends._computer_actions import (
    _clamp_decision, _decision_from_computer_action,
)
from je_auto_control.utils.agent.backends._computer_messages import (
    _attr, _block_type, _final_answer, _raise_if_truncated, _tool_result_content,
)
from je_auto_control.utils.agent.backends._computer_toolset import unscale_decision
from je_auto_control.utils.agent.backends.base import AgentBackendError

_DEFAULT_TOOL_TYPE = "computer_20251124"

#: The beta each computer-use tool version is sent under. Every version is
#: beta-only: posted through the plain ``messages.create`` without one, the
#: API rejects the request, so the backend could never run.
_TOOL_BETAS = {
    "computer_20250124": "computer-use-2025-01-24",
    "computer_20251124": "computer-use-2025-11-24",
}


def beta_for(tool_type: str, beta: Optional[str]) -> str:
    """The beta header for ``tool_type``: the caller's, else the known one."""
    chosen = beta or _TOOL_BETAS.get(tool_type)
    if not chosen:
        raise AgentBackendError(
            f"no known beta for computer-use tool {tool_type!r}; pass beta=")
    return chosen


class BetaToolPath:
    """Reads the beta tool's responses and answers its one call per turn."""

    _conversation: List[Dict[str, Any]]
    _pending_tool_use_id: Optional[str]
    _scale: Tuple[float, float]
    _display: Tuple[int, int]

    def _handle_response(self, response: Any) -> Dict[str, Any]:
        content = list(getattr(response, "content", []) or [])
        self._conversation.append({"role": "assistant", "content": content})
        _raise_if_truncated(response)     # before running any call it holds
        for block in content:
            if _block_type(block) != "tool_use":
                continue
            name = _attr(block, "name")
            if name != "computer":
                # Skipping it made the turn look like a final answer: the run
                # reported success having done nothing the model asked for.
                raise AgentBackendError(
                    f"model called tool {name!r}; only 'computer' was offered",
                )
            payload = _attr(block, "input") or {}
            self._pending_tool_use_id = _attr(block, "id")
            decision = unscale_decision(_decision_from_computer_action(payload), self._scale)
            return _clamp_decision(decision, *self._display)
        return _final_answer(content)

    def _pending_result(self, history: Sequence[AgentStep],
                        screenshot: Optional[bytes]) -> List[Dict[str, Any]]:
        """The ``tool_result`` answering the last turn's call, if one is pending."""
        if not history or self._pending_tool_use_id is None:
            return []
        last = history[-1]
        content = _tool_result_content(last, screenshot, self._scale)
        tool_use_id, self._pending_tool_use_id = self._pending_tool_use_id, None
        return [{
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": bool(last.error),
        }]
