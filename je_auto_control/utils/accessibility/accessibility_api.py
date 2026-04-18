"""Public cross-platform accessibility API.

Target GUI elements by role / name / owning-app rather than pixel
coordinates. The backend is chosen by :func:`get_backend` per platform
and can be swapped out in tests via ``reset_backend_cache``.
"""
from typing import List, Optional

from je_auto_control.utils.accessibility.backends import get_backend
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError, element_matches,
)


def list_accessibility_elements(app_name: Optional[str] = None,
                                max_results: int = 200,
                                ) -> List[AccessibilityElement]:
    """Return a flat list of accessibility elements, optionally filtered."""
    return get_backend().list_elements(
        app_name=app_name, max_results=int(max_results),
    )


def find_accessibility_element(name: Optional[str] = None,
                               role: Optional[str] = None,
                               app_name: Optional[str] = None,
                               ) -> Optional[AccessibilityElement]:
    """First element matching all provided filters, or ``None``."""
    for element in list_accessibility_elements(app_name=app_name):
        if element_matches(element, name=name, role=role, app_name=app_name):
            return element
    return None


def click_accessibility_element(name: Optional[str] = None,
                                role: Optional[str] = None,
                                app_name: Optional[str] = None,
                                ) -> bool:
    """Click the center of the first element matching the filters.

    Returns ``True`` on success, ``False`` if nothing matched. Raises
    :class:`AccessibilityNotAvailableError` if the platform backend is
    missing.
    """
    element = find_accessibility_element(
        name=name, role=role, app_name=app_name,
    )
    if element is None:
        return False
    cx, cy = element.center
    from je_auto_control.wrapper.auto_control_mouse import (
        click_mouse, set_mouse_position,
    )
    set_mouse_position(cx, cy)
    click_mouse("mouse_left", cx, cy)
    return True


__all__ = [
    "AccessibilityElement", "AccessibilityNotAvailableError",
    "list_accessibility_elements", "find_accessibility_element",
    "click_accessibility_element",
]
