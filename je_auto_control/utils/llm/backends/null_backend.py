"""Fallback LLM backend used when nothing real is configured."""
from typing import Optional

from je_auto_control.utils.llm.backends.base import (
    LLMBackend, LLMNotAvailableError,
)


class NullLLMBackend(LLMBackend):
    """Always raises so callers fail fast with a clear message."""

    name = "null"
    available = False

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def complete(self, prompt: str,
                 system: Optional[str] = None,
                 model: Optional[str] = None,
                 max_tokens: int = 2048) -> str:
        del prompt, system, model, max_tokens
        raise LLMNotAvailableError(self._reason)
