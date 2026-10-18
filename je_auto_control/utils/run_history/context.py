"""Explicit history ownership for nested execution and joined workers."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Optional

from je_auto_control.utils.run_history.history_store import HistoryStore


@dataclass(frozen=True)
class HistoryBinding:
    """An existing history row and its owning store; never creates a row itself."""

    store: HistoryStore
    run_id: int


_CURRENT: ContextVar[Optional[HistoryBinding]] = ContextVar("je_auto_control_history_owner", default=None)


def current_history() -> Optional[HistoryBinding]:
    """Return the enclosing execution's history owner, if any."""
    return _CURRENT.get()


@contextmanager
def bound_history(binding: Optional[HistoryBinding]) -> Iterator[None]:
    """Bind an existing owner, or clear ambient ownership; restore on exit."""
    token = _CURRENT.set(binding)
    try:
        yield
    finally:
        _CURRENT.reset(token)
