"""Move / resize UIA elements and drive window state (Transform + Window patterns).

This is **UIA-element-level**, not the HWND/title-level geometry in
``window_layout`` / ``window_geometry``. ``TransformPattern`` moves and resizes a
specific control or floating panel (dockable toolbars, MDI children, splitters)
that has no top-level window of its own; ``WindowPattern`` minimizes / maximizes a
window and — most usefully — reports its **interaction state** (``ready`` /
``blocked_by_modal`` / ``not_responding``), a reliable "is this window ready or
modal-blocked?" signal that pixel or title polling can't give.

* :func:`move_element` / :func:`resize_element` — TransformPattern,
* :func:`set_window_state` — minimize / maximize / restore,
* :func:`window_interaction_state` — the readiness / modal-blocked signal.

Each is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam — headless-testable via a fake backend; the real UIA calls live in the
Windows backend. Imports no ``PySide6``.
"""
from typing import Optional


def _backend():
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend()


def move_element(x: float, y: float, name: Optional[str] = None,
                 role: Optional[str] = None, app_name: Optional[str] = None,
                 automation_id: Optional[str] = None) -> bool:
    """Move the matched element to ``(x, y)`` (TransformPattern); True on success."""
    return _backend().move_element(float(x), float(y), name=name, role=role,
                                   app_name=app_name, automation_id=automation_id)


def resize_element(width: float, height: float, name: Optional[str] = None,
                   role: Optional[str] = None, app_name: Optional[str] = None,
                   automation_id: Optional[str] = None) -> bool:
    """Resize the matched element to ``width`` x ``height`` (TransformPattern)."""
    return _backend().resize_element(float(width), float(height), name=name,
                                     role=role, app_name=app_name,
                                     automation_id=automation_id)


def set_window_state(state: str, name: Optional[str] = None,
                     role: Optional[str] = None, app_name: Optional[str] = None,
                     automation_id: Optional[str] = None) -> bool:
    """Set a window's visual state — ``normal`` / ``maximized`` / ``minimized``."""
    return _backend().set_window_state(str(state), name=name, role=role,
                                       app_name=app_name,
                                       automation_id=automation_id)


def window_interaction_state(name: Optional[str] = None,
                             role: Optional[str] = None,
                             app_name: Optional[str] = None,
                             automation_id: Optional[str] = None) -> Optional[str]:
    """Return a window's interaction state — ``ready`` / ``blocked_by_modal`` /
    ``not_responding`` / ``running`` / ``closing`` (WindowPattern), or None."""
    return _backend().window_interaction_state(name=name, role=role,
                                               app_name=app_name,
                                               automation_id=automation_id)
