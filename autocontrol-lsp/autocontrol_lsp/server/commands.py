"""Discover every ``AC_*`` action command exposed by the executor.

We can't simply hard-code the list because the executor's dispatch
table grows every release. Instead, we introspect ``action_executor``
at runtime (the LSP server is short-lived per session, so the cost
is paid once at startup).
"""
from __future__ import annotations

from typing import Dict, List, Optional


_DISCOVERY_CACHE: Optional[Dict[str, Optional[str]]] = None


def discover_actions() -> Dict[str, Optional[str]]:
    """Return ``{command_name: docstring_or_None}`` for every AC_* command.

    Cached after the first call. Reset by passing ``None`` to
    :func:`_reset_cache` (testing only).
    """
    global _DISCOVERY_CACHE
    if _DISCOVERY_CACHE is not None:
        return _DISCOVERY_CACHE
    try:
        from je_auto_control.utils.executor.action_executor import executor
    except ImportError:
        _DISCOVERY_CACHE = {}
        return _DISCOVERY_CACHE
    out: Dict[str, Optional[str]] = {}
    for name, callable_obj in executor.event_dict.items():
        if not isinstance(name, str) or not name.startswith("AC_"):
            continue
        doc = getattr(callable_obj, "__doc__", None)
        out[name] = doc.strip() if isinstance(doc, str) else None
    _DISCOVERY_CACHE = dict(sorted(out.items()))
    return _DISCOVERY_CACHE


def known_action_names() -> List[str]:
    """Sorted list of every ``AC_*`` command name the executor exposes."""
    return list(discover_actions().keys())


def get_action_doc(name: str) -> Optional[str]:
    """Return the docstring for one command, or None when unknown."""
    return discover_actions().get(name)


def _reset_cache() -> None:
    """Test-only: forget the cached discovery so the next call re-imports."""
    global _DISCOVERY_CACHE
    _DISCOVERY_CACHE = None


__all__ = [
    "discover_actions", "known_action_names", "get_action_doc",
]
