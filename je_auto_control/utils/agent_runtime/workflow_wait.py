"""Bounded, cancellable semantic read-back polling never repeats an input operation."""
from __future__ import annotations

import time
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached, positive
from je_auto_control.utils.agent_runtime.workflow_files import task_policy


def workflow_wait(selector: dict, expected: Any, state: bool = False, timeout_seconds: float = 5) -> Any:
    """Wait for one scoped control's exact value/state without replaying set, invoke or submit."""
    from je_auto_control.utils.agent_runtime.workflow_desktop import workflow_control
    policy = task_policy()
    positive(timeout_seconds, "semantic wait timeout", 60)
    if not isinstance(state, bool):
        raise AgentTaskError("semantic wait state must be boolean")
    expected = detached(expected)
    deadline = time.monotonic() + min(timeout_seconds, policy.spec.budget.action_seconds)
    while True:
        task_policy()
        value = workflow_control("state" if state else "get", selector)
        remaining = deadline - time.monotonic()
        if remaining < 0:
            raise AgentTaskError("semantic read-back arrived after its deadline")
        if value == expected:
            return value
        if remaining <= 0:
            raise AgentTaskError("semantic read-back did not become ready before its deadline")
        time.sleep(min(0.05, remaining))
