"""LLM backend factory.

Mirrors :mod:`je_auto_control.utils.vision.backends`: backends declare
``available`` and ``complete()``; the factory picks the first ready
candidate based on env vars and an optional preference. A null backend is
returned when nothing is configured so callers can detect the situation
through :class:`LLMNotAvailableError` rather than ``ImportError``.
"""
import os
from typing import Optional

from je_auto_control.utils.llm.backends.base import (
    LLMBackend, LLMNotAvailableError,
)
from je_auto_control.utils.llm.backends.null_backend import NullLLMBackend

_cached_backend: Optional[LLMBackend] = None


def get_backend() -> LLMBackend:
    """Return (and cache) an LLM backend chosen by env vars."""
    global _cached_backend
    if _cached_backend is not None:
        return _cached_backend
    _cached_backend = _build_backend()
    return _cached_backend


def reset_backend_cache() -> None:
    """Force ``get_backend()`` to re-detect on its next call."""
    global _cached_backend
    _cached_backend = None


def _build_backend() -> LLMBackend:
    preferred = os.environ.get("AUTOCONTROL_LLM_BACKEND", "").lower()
    for candidate in _preference_order(preferred):
        backend = _try_build(candidate)
        if backend is not None and backend.available:
            return backend
    return NullLLMBackend(
        "no LLM backend ready; set ANTHROPIC_API_KEY and install the "
        "matching SDK (anthropic)",
    )


def _preference_order(preferred: str):
    if preferred == "anthropic":
        return ("anthropic",)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ("anthropic",)
    return ("anthropic",)


def _try_build(name: str) -> Optional[LLMBackend]:
    if name == "anthropic":
        from je_auto_control.utils.llm.backends.anthropic_backend import (
            AnthropicLLMBackend,
        )
        return AnthropicLLMBackend()
    return None


__all__ = [
    "LLMBackend", "LLMNotAvailableError", "NullLLMBackend",
    "get_backend", "reset_backend_cache",
]
