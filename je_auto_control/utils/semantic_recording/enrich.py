"""Annotate recorded actions with anchor metadata for portable replay."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence


_CLICK_ACTIONS = frozenset({
    "mouse_press", "mouse_release", "mouse_click",
})


class AnchorResolver:
    """Pluggable strategy for mapping ``(x, y)`` → semantic anchor.

    The default implementation queries the platform accessibility tree
    via :mod:`je_auto_control.utils.accessibility`. Callers that want a
    VLM-based fallback subclass and override :meth:`resolve` or pass a
    custom ``backend`` callable to the constructor.
    """

    def __init__(self,
                 backend: Optional[Callable[[int, int], Optional[Mapping[str, Any]]]] = None
                 ) -> None:
        self._backend = backend or _default_a11y_backend

    def resolve(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        """Return an anchor dict for the element at ``(x, y)`` or ``None``."""
        try:
            element = self._backend(int(x), int(y))
        except (RuntimeError, OSError):
            return None
        if not element:
            return None
        return dict(element)


def _default_a11y_backend(x: int, y: int) -> Optional[Dict[str, Any]]:
    """Look up the accessibility element whose bounds contain ``(x, y)``."""
    try:
        from je_auto_control.utils.accessibility import (
            AccessibilityNotAvailableError, list_accessibility_elements,
        )
    except ImportError:
        return None
    try:
        elements = list_accessibility_elements()
    except AccessibilityNotAvailableError:
        return None
    best = _smallest_containing(elements, x, y)
    if best is None:
        return None
    return {
        "kind": "a11y",
        "role": best.role,
        "name": best.name,
        "app_name": best.app_name,
        "native_id": best.native_id,
    }


def _smallest_containing(elements, x: int, y: int):
    """Pick the smallest element whose bounding box covers ``(x, y)``.

    "Smallest" because a click usually lands on a button nested inside
    a window — we want the button, not the window.
    """
    candidates = []
    for el in elements:
        left, top, width, height = el.bounds
        if left <= x < left + width and top <= y < top + height:
            candidates.append((width * height, el))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def enrich_action(action: Mapping[str, Any],
                  resolver: Optional[AnchorResolver] = None
                  ) -> Dict[str, Any]:
    """Return a copy of ``action`` with an ``anchor`` field where applicable.

    Only mouse press/release/click actions carrying coordinates get
    anchored — every other action is passed through unchanged.
    """
    out = dict(action)
    if not isinstance(action, Mapping):
        return out
    name = action.get("action")
    if name not in _CLICK_ACTIONS:
        return out
    x = action.get("x")
    y = action.get("y")
    if not isinstance(x, int) or not isinstance(y, int):
        return out
    resolver = resolver or AnchorResolver()
    anchor = resolver.resolve(x, y)
    if anchor:
        out["anchor"] = anchor
    return out


def enrich_recording(actions: Sequence[Mapping[str, Any]],
                     resolver: Optional[AnchorResolver] = None
                     ) -> List[Dict[str, Any]]:
    """Run :func:`enrich_action` over a whole recording."""
    if resolver is None:
        resolver = AnchorResolver()
    return [enrich_action(a, resolver) for a in actions]


__all__ = ["AnchorResolver", "enrich_action", "enrich_recording"]
