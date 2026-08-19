"""Shared ctypes plumbing for the Wayland native bindings.

``libei`` and ``liboeffis`` are reached the same way: find the shared object
on the loader path, resolve a table of entry points with explicit prototypes,
and expose them by name so a test can substitute any object carrying the same
attributes. Keeping one copy matters more than the few lines it saves — a
second copy is a second place for a prototype to drift away from the header
it was written from.
"""
from __future__ import annotations

import ctypes
import ctypes.util
from typing import Any, Iterable, Optional, Sequence, Tuple


#: ``(name, restype, argtypes)`` as ctypes wants them.
Prototype = Tuple[str, Any, tuple]


class BoundSymbols:
    """Entry points resolved out of one shared object, addressed by name."""

    def __init__(self, lib: ctypes.CDLL, prototypes: Iterable[Prototype], *,
                 unchecked: Sequence[str] = ()) -> None:
        self._fn = {}
        self.lib = lib
        for name, restype, argtypes in prototypes:
            entry = getattr(lib, name)
            entry.restype = restype
            entry.argtypes = argtypes
            self._fn[name] = entry
        for name in unchecked:
            # Variadic entry points: ctypes has to infer each argument's type
            # at the call site, so an argtypes tuple would be wrong here.
            self._fn[name] = getattr(lib, name)

    def __getattr__(self, name: str):
        try:
            return self._fn[name]
        except KeyError:
            raise AttributeError(name) from None


def load_library(candidates: Iterable[str]) -> Optional[ctypes.CDLL]:
    """Return the first of ``candidates`` that loads, or None if none do."""
    for name in candidates:
        resolved = ctypes.util.find_library(name)
        if resolved is None:
            continue
        try:
            return ctypes.CDLL(resolved, use_errno=True)
        except (OSError, RuntimeError):
            continue
    return None


def bind(candidates: Iterable[str], prototypes: Iterable[Prototype], *,
         unchecked: Sequence[str] = ()) -> Optional[BoundSymbols]:
    """Load a library and resolve its prototypes, or None if either fails.

    A missing entry point means the installed library is not the one these
    prototypes were written for, which is a "not available" rather than an
    error the caller should have to handle separately.
    """
    lib = load_library(candidates)
    if lib is None:
        return None
    try:
        return BoundSymbols(lib, prototypes, unchecked=unchecked)
    except AttributeError:
        return None


__all__ = ["BoundSymbols", "Prototype", "bind", "load_library"]
