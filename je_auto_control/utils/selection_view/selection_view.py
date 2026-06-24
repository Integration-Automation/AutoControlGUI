"""Container selection state + view switching (Selection / MultipleView patterns).

``select_control_item`` (SelectionItemPattern) selects *one* item; the
container-level ``SelectionPattern`` answers the natural follow-up — **what is
currently selected** in a listbox / grid / tab, and **may it select multiple?** —
the assertion target after selecting. ``MultipleViewPattern`` switches a control
between its views (Explorer's list / details / tile / thumbnail), a common
precondition that otherwise needs fragile menu clicking.

* :func:`get_selection` — ``{items, can_select_multiple, is_required}``,
* :func:`list_views` — ``{current, views: [...]}``,
* :func:`set_view` — switch to a named view.

Each is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam — headless-testable via a fake backend; the real UIA calls live in the
Windows backend. Imports no ``PySide6``.
"""
from typing import Any, Dict, Optional


def _backend():
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend()


def get_selection(name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None,
                  ) -> Optional[Dict[str, Any]]:
    """Return a container's selection state — ``{items, can_select_multiple,
    is_required}`` (SelectionPattern), or None if not found."""
    return _backend().get_selection(name=name, role=role, app_name=app_name,
                                    automation_id=automation_id)


def list_views(name: Optional[str] = None, role: Optional[str] = None,
               app_name: Optional[str] = None,
               automation_id: Optional[str] = None,
               ) -> Optional[Dict[str, Any]]:
    """Return a control's selectable views — ``{current, views: [...]}``
    (MultipleViewPattern), or None if not found."""
    return _backend().list_views(name=name, role=role, app_name=app_name,
                                 automation_id=automation_id)


def set_view(view: str, name: Optional[str] = None, role: Optional[str] = None,
             app_name: Optional[str] = None,
             automation_id: Optional[str] = None) -> bool:
    """Switch a control to the named view (MultipleViewPattern); True on success."""
    return _backend().set_view(str(view), name=name, role=role,
                               app_name=app_name, automation_id=automation_id)
