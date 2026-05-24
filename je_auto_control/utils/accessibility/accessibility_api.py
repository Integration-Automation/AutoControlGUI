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
from je_auto_control.utils.accessibility.tree import AXTreeNode


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


def dump_accessibility_tree(app_name: Optional[str] = None,
                             max_results: int = 500) -> AXTreeNode:
    """Return a flat-but-nested-by-app tree dump.

    Backends that don't expose a true parent-child API (yet) emit a
    flat list under one synthetic root per app, so callers can still
    pretty-print / iterate predictably until a true hierarchical
    walker lands per platform.
    """
    elements = list_accessibility_elements(
        app_name=app_name, max_results=int(max_results),
    )
    by_app: dict = {}
    for element in elements:
        app = element.app_name or "(unknown)"
        by_app.setdefault(app, []).append(element)
    children = []
    for app, items in sorted(by_app.items()):
        children.append(AXTreeNode(
            name=app, role="AXApplication",
            bounds=(0, 0, 0, 0),
            app_name=app,
            children=[AXTreeNode(
                name=el.name, role=el.role,
                bounds=tuple(el.bounds),
                app_name=el.app_name,
                process_id=int(el.process_id),
            ) for el in items],
        ))
    root_app = app_name or "(all)"
    return AXTreeNode(
        name=root_app, role="AXRoot", bounds=(0, 0, 0, 0),
        app_name=root_app, children=children,
    )


__all__ = [
    "AccessibilityElement", "AccessibilityNotAvailableError",
    "AXTreeNode",
    "click_accessibility_element", "dump_accessibility_tree",
    "find_accessibility_element", "list_accessibility_elements",
]
