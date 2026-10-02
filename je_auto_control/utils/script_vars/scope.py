"""Runtime variable scope for the action executor.

Pre-execution interpolation in :mod:`interpolate` replaces ``${var}``
placeholders once, against a static mapping. Some scripts need to mutate
state during execution — counters in loops, captured OCR/locator results,
``for_each`` items. ``VariableScope`` is a thin mutable container the
executor exposes to flow-control commands so those commands can read and
write the same bag the runtime interpolator consults.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any, Dict, Iterator, Mapping, MutableMapping, Optional


class VariableScope(MutableMapping[str, Any]):
    """Mutable mapping of script variables shared across action execution."""

    __slots__ = ("_vars",)

    def __init__(self, initial: Optional[Mapping[str, Any]] = None) -> None:
        self._vars: Dict[str, Any] = dict(initial) if initial else {}

    def __getitem__(self, key: str) -> Any:
        return self._vars[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if not isinstance(key, str) or not key:
            raise ValueError("variable name must be a non-empty string")
        self._vars[key] = value

    def __delitem__(self, key: str) -> None:
        del self._vars[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._vars)

    def __len__(self) -> int:
        return len(self._vars)

    def __contains__(self, key: object) -> bool:
        return key in self._vars

    def set(self, name: str, value: Any) -> None:
        """Assign ``name`` to ``value``."""
        self[name] = value

    def get_value(self, name: str, default: Any = None) -> Any:
        """Return the variable, or ``default`` when missing."""
        return self._vars.get(name, default)

    def update_many(self, mapping: Mapping[str, Any]) -> None:
        """Bulk-assign from a mapping; nothing is assigned when any name is invalid.

        A ``""`` key raised after the names before it were already set.
        """
        items = list(mapping.items())
        for key, _value in items:
            if not isinstance(key, str) or not key:
                raise ValueError("variable name must be a non-empty string")
        for key, value in items:
            self._vars[key] = value

    def as_dict(self) -> Dict[str, Any]:
        """Return a shallow copy as a plain dict (safe for interpolation)."""
        return dict(self._vars)

    def fork(self) -> "VariableScope":
        """Deep-copy branch variables so mutable values cannot alter the parent."""
        return VariableScope(deepcopy(self._vars))

    def clear(self) -> None:
        """Drop every stored variable."""
        self._vars.clear()


_EXECUTION_SCOPE: ContextVar[Optional[VariableScope]] = ContextVar(
    "autocontrol_execution_scope", default=None,
)


def current_execution_scope() -> Optional[VariableScope]:
    """Return this context's active variables, or None outside a public run."""
    return _EXECUTION_SCOPE.get()


@contextmanager
def execution_scope(variables: Optional[Mapping[str, object]] = None, *,
                    isolated: bool = False) -> Iterator[VariableScope]:
    """Isolate a public run; nested calls share its variables and restore on exit.

    Each parallel worker starts its own context with a snapshot of the parent.
    Use this boundary explicitly to share variables across several public calls.
    ``isolated=True`` forks a worker even if its thread inherits the context.
    """
    active = current_execution_scope()
    if active is not None and not isolated:
        if variables is not None:
            active.update_many(variables)
        yield active
        return
    scope = VariableScope()
    if variables is not None:
        scope.update_many(variables)
    if isolated:
        scope = scope.fork()
    token = _EXECUTION_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _EXECUTION_SCOPE.reset(token)
