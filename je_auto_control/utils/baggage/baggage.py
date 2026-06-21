"""W3C Baggage propagation (cross-cutting key-value context).

The just-shipped ``trace_context`` carries trace/span identity across an HTTP
boundary, but there was no way to propagate cross-cutting key-value context
(``run_id`` / ``tenant`` / ``experiment``) alongside it. This implements the
W3C Baggage header — a percent-encoded ``key=value`` list — so a run can attach
such context to outgoing requests and read it back on the other side.

Pure standard library (``urllib.parse``); imports no ``PySide6``. ``Baggage`` is
immutable (mutators return a new instance), so propagation is deterministic in
CI.
"""
from typing import Dict, List, Mapping, Optional, Tuple
from urllib.parse import quote, unquote

_MAX_ENTRIES = 180


class Baggage:
    """An immutable set of W3C baggage key-value entries."""

    def __init__(self, items: Optional[Mapping[str, str]] = None) -> None:
        self._items: Dict[str, str] = {str(key): str(value)
                                       for key, value in (items or {}).items()}

    def to_dict(self) -> Dict[str, str]:
        """Return the entries as a plain dict."""
        return dict(self._items)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Return the value for ``key`` or ``default``."""
        return self._items.get(key, default)

    def set(self, key: str, value: str) -> "Baggage":
        """Return a new baggage with ``key`` set to ``value``."""
        updated = dict(self._items)
        updated[str(key)] = str(value)
        return Baggage(updated)

    def remove(self, key: str) -> "Baggage":
        """Return a new baggage with ``key`` removed."""
        updated = dict(self._items)
        updated.pop(key, None)
        return Baggage(updated)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Baggage) and other._items == self._items

    def __repr__(self) -> str:
        return f"Baggage({self._items!r})"


def _parse_member(member: str) -> Optional[Tuple[str, str]]:
    pair = member.split(";", 1)[0].strip()    # drop optional ;metadata
    if not pair:
        return None
    key, sep, value = pair.partition("=")
    if not sep or not key.strip():
        return None
    return unquote(key.strip()), unquote(value.strip())


def parse_baggage(header: Optional[str]) -> Baggage:
    """Parse a W3C ``baggage`` header into a :class:`Baggage`."""
    items: Dict[str, str] = {}
    for member in (header or "").split(","):
        parsed = _parse_member(member)
        if parsed is not None:
            items[parsed[0]] = parsed[1]
    return Baggage(items)


def format_baggage(baggage: Baggage) -> str:
    """Serialise a :class:`Baggage` into a percent-encoded header value."""
    parts: List[str] = []
    for key, value in list(baggage.to_dict().items())[:_MAX_ENTRIES]:
        parts.append(f"{quote(key, safe='')}={quote(value, safe='')}")
    return ",".join(parts)


def inject_baggage(headers: Optional[Dict[str, str]],
                   baggage: Baggage) -> Dict[str, str]:
    """Return ``headers`` with the ``baggage`` header set (when non-empty)."""
    out = dict(headers or {})
    encoded = format_baggage(baggage)
    if encoded:
        out["baggage"] = encoded
    return out


def extract_baggage(headers: Optional[Dict[str, str]]) -> Baggage:
    """Extract a :class:`Baggage` from request headers (case-insensitive)."""
    for key, value in (headers or {}).items():
        if str(key).lower() == "baggage":
            return parse_baggage(value)
    return Baggage()
