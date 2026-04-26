"""LLM-driven natural-language → action-list planning.

The planner asks an LLM (default: Anthropic Claude) to translate a
description like ``"open Notepad, type hello, save as test.txt"`` into a
validated JSON action list using the executor's known ``AC_*`` commands.
The result is structurally validated before it is returned, so callers can
feed it straight into the executor.
"""
from je_auto_control.utils.llm.backends import (
    LLMBackend, LLMNotAvailableError, get_backend, reset_backend_cache,
)
from je_auto_control.utils.llm.planner import (
    LLMPlanError, plan_actions, run_from_description,
)

__all__ = [
    "LLMBackend", "LLMNotAvailableError", "LLMPlanError",
    "get_backend", "reset_backend_cache",
    "plan_actions", "run_from_description",
]
