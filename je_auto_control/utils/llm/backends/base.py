"""Common protocol shared by every LLM backend."""
from typing import Optional


class LLMNotAvailableError(RuntimeError):
    """Raised when no LLM backend is configured / reachable."""


class LLMBackend:
    """Minimal text-completion contract used by the action planner."""

    name: str = "base"
    available: bool = False

    def complete(self, prompt: str,
                 system: Optional[str] = None,
                 model: Optional[str] = None,
                 max_tokens: int = 2048) -> str:
        """Return the model's text response for ``prompt``.

        Backends should return an empty string (not raise) on transient
        failures so the planner can surface a deterministic error.
        """
        raise NotImplementedError
