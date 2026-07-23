"""Consistent deprecation warnings for public AutoControl APIs."""
from __future__ import annotations

import functools
import warnings
from typing import Callable, TypeVar, cast

F = TypeVar("F", bound=Callable)


class AutoControlDeprecationWarning(FutureWarning):
    """A user-visible warning for an API scheduled for removal."""


def deprecated(*, since: str, removal: str, replacement: str = ""):
    """Mark a callable deprecated with actionable lifecycle metadata."""
    def decorate(func: F) -> F:
        message = f"{func.__qualname__} is deprecated since {since}"
        message += f" and will be removed in {removal}."
        if replacement:
            message += f" Use {replacement} instead."

        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            warnings.warn(message, AutoControlDeprecationWarning,
                          stacklevel=2)
            return func(*args, **kwargs)
        wrapped.__deprecated__ = {  # type: ignore[attr-defined]
            "since": since, "removal": removal, "replacement": replacement,
        }
        return cast(F, wrapped)
    return decorate


__all__ = ["AutoControlDeprecationWarning", "deprecated"]
