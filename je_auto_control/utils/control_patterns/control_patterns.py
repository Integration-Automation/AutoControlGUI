"""Extended UI Automation control-pattern actions (Expand / Select / Range / Scroll).

The accessibility backend ships only four control patterns — Value, Invoke, Toggle and a
read-only Grid dump. That leaves the controls automation hits most often undriveable by their
*native* pattern: a treeview node can't be expanded, a listbox / combobox item can't be
selected (SelectionItemPattern), a slider can't be set (RangeValuePattern), and a control can't
be scrolled into view (ScrollItemPattern) — today those fall back to fragile pixel guessing.
``control_patterns`` adds those object-level actions on top of the existing backend ABC.

Each function is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam (the same seam the rest of the accessibility module uses), so the headless core is
unit-testable on any platform by injecting a fake backend; the real UIA calls live in the
Windows backend. Imports no ``PySide6``.
"""
from typing import Any, Dict, Optional


def _backend():
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend()


def expand_control(name: Optional[str] = None, role: Optional[str] = None,
                   app_name: Optional[str] = None,
                   automation_id: Optional[str] = None) -> bool:
    """Expand a tree node / combobox / expander (ExpandCollapsePattern)."""
    return _backend().expand(name=name, role=role, app_name=app_name,
                             automation_id=automation_id)


def collapse_control(name: Optional[str] = None, role: Optional[str] = None,
                     app_name: Optional[str] = None,
                     automation_id: Optional[str] = None) -> bool:
    """Collapse a tree node / combobox / expander (ExpandCollapsePattern)."""
    return _backend().collapse(name=name, role=role, app_name=app_name,
                               automation_id=automation_id)


def control_expand_state(name: Optional[str] = None, role: Optional[str] = None,
                         app_name: Optional[str] = None,
                         automation_id: Optional[str] = None) -> Optional[str]:
    """Return ``expanded`` / ``collapsed`` / ``partial`` / ``leaf`` for a control."""
    return _backend().expand_state(name=name, role=role, app_name=app_name,
                                   automation_id=automation_id)


def select_control_item(name: Optional[str] = None, role: Optional[str] = None,
                        app_name: Optional[str] = None,
                        automation_id: Optional[str] = None) -> bool:
    """Select a list / tree / tab item (SelectionItemPattern)."""
    return _backend().select_item(name=name, role=role, app_name=app_name,
                                  automation_id=automation_id)


def control_range(name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return ``{value, minimum, maximum}`` of a slider / progress (RangeValuePattern)."""
    return _backend().get_range(name=name, role=role, app_name=app_name,
                                automation_id=automation_id)


def set_control_range(value: float, name: Optional[str] = None,
                      role: Optional[str] = None, app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> bool:
    """Set a slider / progress / spinner value (RangeValuePattern)."""
    return _backend().set_range_value(float(value), name=name, role=role,
                                      app_name=app_name,
                                      automation_id=automation_id)


def scroll_control_into_view(name: Optional[str] = None, role: Optional[str] = None,
                             app_name: Optional[str] = None,
                             automation_id: Optional[str] = None) -> bool:
    """Scroll a control into view before acting on it (ScrollItemPattern)."""
    return _backend().scroll_into_view(name=name, role=role, app_name=app_name,
                                       automation_id=automation_id)
