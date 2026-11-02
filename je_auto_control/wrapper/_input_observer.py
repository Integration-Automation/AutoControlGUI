"""Opt-in native input notifications; unscoped legacy operations retain their behavior."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

_OBSERVER: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar("native_input_observer", default=None)


def has_input_observer() -> bool:
    """Whether native input must expose individually owned press/release boundaries."""
    return _OBSERVER.get() is not None


@contextmanager
def input_observer(callback: Callable[[dict[str, Any]], None]) -> Iterator[None]:
    """Bind an owned helper's observer without installing any global OS hook."""
    token = _OBSERVER.set(callback)
    try:
        yield
    finally:
        _OBSERVER.reset(token)


def input_event(kind: str, **values: Any) -> None:
    """Notify before a press and after a successful release; refusal prevents new input."""
    callback = _OBSERVER.get()
    if callback is not None:
        callback({"kind": kind, **values})
