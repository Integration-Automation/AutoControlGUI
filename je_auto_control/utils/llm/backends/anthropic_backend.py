"""Anthropic (Claude) text-completion backend for the action planner."""
import os
from typing import Optional

from je_auto_control.utils.llm.backends.base import LLMBackend
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_DEFAULT_MODEL = "claude-opus-4-7"
_REQUEST_TIMEOUT_S = 60.0


class AnthropicLLMBackend(LLMBackend):
    """Call ``claude-*`` chat models via the ``anthropic`` Python SDK."""

    name = "anthropic"

    def __init__(self) -> None:
        self._client = None
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.available = False
            return
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.available = False
            return
        try:
            from anthropic import Anthropic
            self._client = Anthropic()
            self.available = True
        except (ImportError, ValueError, RuntimeError) as error:
            autocontrol_logger.warning(
                "Anthropic LLM client init failed: %r", error,
            )
            self.available = False

    def complete(self, prompt: str,
                 system: Optional[str] = None,
                 model: Optional[str] = None,
                 max_tokens: int = 2048) -> str:
        if not self.available or self._client is None:
            return ""
        chosen_model = (model
                        or os.environ.get("AUTOCONTROL_LLM_MODEL")
                        or _DEFAULT_MODEL)
        kwargs = {
            "model": chosen_model,
            "max_tokens": int(max_tokens),
            "timeout": _REQUEST_TIMEOUT_S,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        try:
            response = self._client.messages.create(**kwargs)
        except (OSError, ValueError, RuntimeError) as error:
            autocontrol_logger.warning(
                "Anthropic LLM request failed: %r", error,
            )
            return ""
        return _join_text_blocks(response)


def _join_text_blocks(response) -> str:
    """Concatenate every text block in an Anthropic response."""
    parts = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
            if text:
                parts.append(text)
    return "".join(parts)
