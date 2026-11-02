"""Bounded workspace bootstrap only focuses explicitly approved application windows."""
from __future__ import annotations

import time
from typing import Any

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, thaw


def bootstrap_allowed(spec: AgentTaskSpec | None) -> bool:
    """Allow inert bootstrap observations for reviewed plans containing explicit window focus."""
    return bool(spec is not None and spec.apps and any(action["tool"] == "AC_focus_window" for action in spec.actions))


def focus_approved(spec: AgentTaskSpec | None, arguments: dict) -> Any:
    """Wait for one approved application window without touching an unrelated foreground app."""
    from je_auto_control.utils.agent_runtime.native_scope import check_window_arguments
    from je_auto_control.utils.tool_use_schema import run_tool_call
    if spec is None or not any(action["tool"] == "AC_focus_window" and thaw(action["arguments"]) == arguments
                               for action in spec.actions):
        raise AgentTaskError("bootstrap focus must match an explicitly approved plan action")
    operation = current_operation()
    if operation is None:
        raise AgentTaskError("bootstrap focus requires a managed operation")
    deadline = time.monotonic() + spec.budget.action_seconds
    while time.monotonic() < deadline:
        operation.checkpoint()
        try:
            check_window_arguments(arguments, spec)
        except AgentTaskError:
            time.sleep(0.05)
            continue
        return run_tool_call("AC_focus_window", arguments)
    raise AgentTaskError("approved application window did not become ready before its deadline")
