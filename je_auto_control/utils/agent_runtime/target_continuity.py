"""Require a live UI target context before trusting a finite skill's verified prefix."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from je_auto_control.utils.agent_runtime.errors import AgentHumanReview
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.receipts import effective_actions


def require_context_continuity(spec: AgentTaskSpec, receipts: Sequence[Mapping[str, Any]], connected: bool,
                               *, kind: str) -> None:
    """Retired UI state cannot be reconstructed by confirmed historical field receipts."""
    if spec.mode == "skill" and not connected and effective_actions(receipts):
        raise AgentHumanReview(
            f"{kind} context ended; review remaining actions and create a new task before continuing")
