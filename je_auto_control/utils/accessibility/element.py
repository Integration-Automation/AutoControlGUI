"""Shared dataclasses and exceptions for the accessibility API."""
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class AccessibilityElement:
    """A GUI element exposed through the platform's accessibility tree.

    Coordinates are in screen pixels; ``(left, top, width, height)``.
    ``app_name`` / ``process_id`` identify the owning application.
    """
    name: str
    role: str
    bounds: Tuple[int, int, int, int]
    app_name: str = ""
    process_id: int = 0
    native_id: str = ""
    # A disabled control looks clickable and silently ignores the click, so
    # this is worth carrying on every element rather than asking per element.
    enabled: bool = True

    @property
    def center(self) -> Tuple[int, int]:
        left, top, width, height = self.bounds
        return (left + width // 2, top + height // 2)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "role": self.role,
            "bounds": list(self.bounds),
            "app_name": self.app_name, "process_id": self.process_id,
            "native_id": self.native_id, "enabled": self.enabled,
            "center": list(self.center),
        }


class AccessibilityNotAvailableError(RuntimeError):
    """Raised when the platform backend cannot be initialised."""


def _role_matches(actual: str, wanted: str) -> bool:
    """Compare roles by either spelling.

    The Windows backend reports the raw UIA role (``ControlType_50000``) on
    purpose — translation is a separate step — but nobody filtering a search
    types that. Without accepting the friendly name, ``role="button"`` matches
    nothing on Windows and reports it as "not found" rather than as a mistake.
    """
    if actual.lower() == wanted.lower():
        return True
    from je_auto_control.utils.ax_tree_walk.ax_tree_walk import humanize_role
    return humanize_role(actual).lower() == humanize_role(wanted).lower()


def element_matches(element: AccessibilityElement,
                    name: Optional[str] = None,
                    role: Optional[str] = None,
                    app_name: Optional[str] = None,
                    contains: bool = False) -> bool:
    """Return True if ``element`` matches all non-None filters.

    ``contains`` compares ``name`` case-insensitively as a *substring*. Real
    interfaces label controls with accelerator markers and trailing padding
    (``Save(&S)``, ``OK ``), so an exact comparison misses a large share of
    genuine targets — but exact stays the default, because a caller that
    already holds a full name must keep getting exactly that element.
    """
    if name is not None:
        if contains:
            if name.strip().lower() not in element.name.lower():
                return False
        elif element.name != name:
            return False
    if role is not None and not _role_matches(element.role, role):
        return False
    if app_name is not None and element.app_name != app_name:
        return False
    return True


def rank_by_name(elements: List[AccessibilityElement],
                 name: str) -> List[AccessibilityElement]:
    """Order substring hits so an exact name wins, then reading order.

    Searching "OK" should offer the ``OK`` button before ``OK and close``;
    without the ordering the caller clicks whichever the tree happened to
    enumerate first, which is neither stable nor what was asked for.
    """
    needle = (name or "").strip().lower()

    def _key(element: AccessibilityElement):
        left, top, _width, _height = element.bounds
        return (element.name.strip().lower() != needle, top, left)

    return sorted(elements, key=_key)
