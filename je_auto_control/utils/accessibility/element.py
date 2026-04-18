"""Shared dataclasses and exceptions for the accessibility API."""
from dataclasses import dataclass
from typing import Optional, Tuple


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

    @property
    def center(self) -> Tuple[int, int]:
        left, top, width, height = self.bounds
        return (left + width // 2, top + height // 2)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "role": self.role,
            "bounds": list(self.bounds),
            "app_name": self.app_name, "process_id": self.process_id,
            "native_id": self.native_id,
            "center": list(self.center),
        }


class AccessibilityNotAvailableError(RuntimeError):
    """Raised when the platform backend cannot be initialised."""


def element_matches(element: AccessibilityElement,
                    name: Optional[str] = None,
                    role: Optional[str] = None,
                    app_name: Optional[str] = None) -> bool:
    """Return True if ``element`` matches all non-None filters."""
    if name is not None and element.name != name:
        return False
    if role is not None and element.role.lower() != role.lower():
        return False
    if app_name is not None and element.app_name != app_name:
        return False
    return True
