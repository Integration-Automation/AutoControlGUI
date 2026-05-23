"""Phase 6.7: replay-anywhere — re-locate anchored actions on a fresh host.

A recording produced by :func:`enrich_recording` carries an ``anchor``
field on each click describing the UI element by accessibility role +
name (and optionally other identifiers). At replay time this module:

1. Looks up the live element matching that anchor on the current host.
2. Rewrites the action's ``x`` / ``y`` to the element's center.
3. Falls back to the original coordinates if the lookup fails — so a
   replay never gets stuck because an unrelated app moved.

The implementation is pluggable: pass a custom ``locator`` callable to
swap in VLM-backed or image-template lookup when accessibility is not
available (e.g. on a stock Linux without AT-SPI).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple


_CLICK_ACTIONS = frozenset({
    "mouse_press", "mouse_release", "mouse_click",
})


class AnchorLocator:
    """Resolve an anchor dict back to a ``(x, y)`` on the current screen.

    The default locator uses :mod:`je_auto_control.utils.accessibility`
    to find an element matching the anchor's ``role`` and ``name``.
    Override or replace via the ``backend`` constructor argument.
    """

    def __init__(self,
                 backend: Optional[Callable[[Mapping[str, Any]], Optional[Tuple[int, int]]]] = None
                 ) -> None:
        self._backend = backend or _default_a11y_locator

    def locate(self, anchor: Mapping[str, Any]) -> Optional[Tuple[int, int]]:
        try:
            return self._backend(anchor)
        except (RuntimeError, OSError):
            return None


def _default_a11y_locator(anchor: Mapping[str, Any]
                          ) -> Optional[Tuple[int, int]]:
    """Find an accessibility element matching the anchor's name / role."""
    if anchor.get("kind") not in (None, "a11y"):
        return None
    try:
        from je_auto_control.utils.accessibility import (
            AccessibilityNotAvailableError, find_accessibility_element,
        )
    except ImportError:
        return None
    try:
        element = find_accessibility_element(
            name=anchor.get("name") or None,
            role=anchor.get("role") or None,
            app_name=anchor.get("app_name") or None,
        )
    except AccessibilityNotAvailableError:
        return None
    if element is None:
        return None
    return element.center


def relocate_action(action: Mapping[str, Any],
                    locator: Optional[AnchorLocator] = None
                    ) -> Dict[str, Any]:
    """Return a copy of ``action`` with ``x``/``y`` rewritten from its anchor.

    No-op when the action has no anchor or the lookup failed. Adds a
    ``relocated`` boolean so logs / tests can distinguish the path.
    """
    out = dict(action)
    if action.get("action") not in _CLICK_ACTIONS:
        return out
    anchor = action.get("anchor")
    if not isinstance(anchor, Mapping):
        return out
    locator = locator or AnchorLocator()
    pos = locator.locate(anchor)
    if pos is None:
        out["relocated"] = False
        return out
    new_x, new_y = pos
    out["x"] = int(new_x)
    out["y"] = int(new_y)
    out["relocated"] = True
    return out


def relocate_recording(actions: Sequence[Mapping[str, Any]],
                       locator: Optional[AnchorLocator] = None
                       ) -> List[Dict[str, Any]]:
    """Run :func:`relocate_action` across the whole recording."""
    if locator is None:
        locator = AnchorLocator()
    return [relocate_action(a, locator) for a in actions]


__all__ = ["AnchorLocator", "relocate_action", "relocate_recording"]
