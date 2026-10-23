"""Intersect context-local vault access guards before resolving any ambient secret namespace."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator

_GUARDS: ContextVar[tuple[Callable[[str], None], ...]] = ContextVar("vault_access_guards", default=())


@contextmanager
def _vault_guard(check: Callable[[str], None]) -> Iterator[None]:
    token = _GUARDS.set((*_GUARDS.get(), check))
    try:
        yield
    finally:
        _GUARDS.reset(token)


def _check_vault_access(name: str) -> None:
    for check in _GUARDS.get():
        check(name)
