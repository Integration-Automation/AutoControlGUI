"""Realize off-screen items in virtualized lists / grids / trees.

Long lists, data grids and trees (WPF / WinUI / Explorer / virtual treeviews)
only materialize the rows that are scrolled into view — a row that is off-screen
has *no* accessibility element at all, so ``list_accessibility_elements`` /
``read_control_table`` / ``select_control_item`` simply cannot see it, and
``scroll_control_into_view`` can't help because the target doesn't exist yet.

``realize_item`` closes that gap: it locates the item inside its container by
property (UI Automation ``ItemContainerPattern``) and realizes it
(``VirtualizedItemPattern``) so it materializes as a real element you can then
click / read. It is a thin dispatch onto the injectable
``accessibility.backends.get_backend()`` seam — headless-testable on any platform
by injecting a fake backend; the real UIA calls live in the Windows backend.
Imports no ``PySide6``.
"""
from typing import Optional

from je_auto_control.utils.accessibility.element import AccessibilityElement


def realize_item(item_name: str, *, by: str = "name",
                 container_name: Optional[str] = None,
                 container_role: Optional[str] = None,
                 app_name: Optional[str] = None,
                 automation_id: Optional[str] = None,
                 ) -> Optional[AccessibilityElement]:
    """Find and realize a virtualized item, returning its element (or None).

    ``item_name`` is matched against the item's Name (``by="name"``) or its
    AutomationId (``by="automation_id"``). The container is located by
    ``container_name`` / ``container_role`` / ``app_name`` / ``automation_id``
    (the same matchers as the other native-control actions).
    """
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend().find_virtual_item(
        item_name, by=by, container_name=container_name,
        container_role=container_role, app_name=app_name,
        automation_id=automation_id)
