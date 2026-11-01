"""VLM backend factory."""
import os
from typing import Optional

from je_auto_control.utils.vision.backends.base import (
    VLMBackend, VLMNotAvailableError,
)
from je_auto_control.utils.vision.backends.null_backend import NullVLMBackend

_cached_backend: Optional[VLMBackend] = None


def get_backend() -> VLMBackend:
    """Return (and cache) a VLM backend chosen by env vars."""
    global _cached_backend
    if _cached_backend is not None:
        return _cached_backend
    _cached_backend = _build_backend()
    return _cached_backend


def reset_backend_cache() -> None:
    """Force ``get_backend()`` to re-detect on its next call."""
    global _cached_backend
    _cached_backend = None


def _build_backend() -> VLMBackend:
    preferred = os.environ.get("AUTOCONTROL_VLM_BACKEND", "").lower()
    order = _preference_order(preferred)
    for candidate in order:
        backend = _try_build(candidate)
        if backend is not None and backend.available:
            return backend
    return NullVLMBackend(
        "no VLM backend ready; set ANTHROPIC_API_KEY or OPENAI_API_KEY "
        "and install the matching SDK (anthropic / openai)",
    )


def _preference_order(preferred: str):
    if preferred == "anthropic":
        return ("anthropic", "openai")
    if preferred == "openai":
        return ("openai", "anthropic")
    if os.environ.get("ANTHROPIC_API_KEY"):
        return ("anthropic", "openai")
    if os.environ.get("OPENAI_API_KEY"):
        return ("openai", "anthropic")
    return ("anthropic", "openai")


def _try_build(name: str):
    if name == "anthropic":
        from je_auto_control.utils.vision.backends.anthropic_backend import (
            AnthropicVLMBackend,
        )
        return AnthropicVLMBackend()
    if name == "openai":
        from je_auto_control.utils.vision.backends.openai_backend import (
            OpenAIVLMBackend,
        )
        return OpenAIVLMBackend()
    return None


BACKEND_NAMES = ("anthropic", "openai", "null")


def backend_by_name(name: str) -> VLMBackend:
    """A new backend chosen by name: ``anthropic``, ``openai`` or ``null``.

    ``null`` is the backend that refuses every request, which is what an
    evaluation on a machine with no key should measure. An SDK that is not
    installed, or a missing key, gives a backend whose ``available`` is false.
    """
    if name == "null":
        return NullVLMBackend("the null VLM backend answers nothing")
    backend = _try_build(str(name).lower())
    if backend is None:
        raise VLMNotAvailableError(
            f"unknown VLM backend {name!r}; known: {list(BACKEND_NAMES)}")
    return backend


__all__ = [
    "BACKEND_NAMES", "VLMBackend", "VLMNotAvailableError", "NullVLMBackend",
    "backend_by_name", "get_backend", "reset_backend_cache",
]
