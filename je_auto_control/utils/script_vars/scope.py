"""Runtime variable scope for the action executor.

Pre-execution interpolation in :mod:`interpolate` replaces ``${var}``
placeholders once, against a static mapping. Some scripts need to mutate
state during execution — counters in loops, captured OCR/locator results,
``for_each`` items. ``VariableScope`` is a thin mutable container the
executor exposes to flow-control commands so those commands can read and
write the same bag the runtime interpolator consults.
"""
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
        """Bulk-assign from a mapping."""
        for key, value in mapping.items():
            self[key] = value

    def as_dict(self) -> Dict[str, Any]:
        """Return a shallow copy as a plain dict (safe for interpolation)."""
        return dict(self._vars)

    def clear(self) -> None:
        """Drop every stored variable."""
        self._vars.clear()
