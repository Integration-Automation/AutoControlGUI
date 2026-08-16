"""Public cross-platform accessibility API.

Target GUI elements by role / name / owning-app rather than pixel
coordinates. The backend is chosen by :func:`get_backend` per platform
and can be swapped out in tests via ``reset_backend_cache``.
"""
from typing import Any, Dict, List, Optional, Tuple

from je_auto_control.utils.accessibility.backends import get_backend
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError, element_matches,
    rank_by_name,
)
from je_auto_control.utils.accessibility.tree import AXTreeNode


def accessibility_status() -> Tuple[bool, str]:
    """``(usable, reason)`` for the platform's accessibility backend.

    A predicate rather than the backend object, so callers can report "not
    available, and here is why" without reaching into the backend layer or
    provoking an exception to find out.
    """
    backend = get_backend()
    if getattr(backend, "available", False):
        return True, f"{backend.name} backend ready"
    return False, getattr(backend, "_reason", "no accessibility backend available")


def list_accessibility_elements(app_name: Optional[str] = None,
                                max_results: int = 200,
                                window_title: Optional[str] = None,
                                ) -> List[AccessibilityElement]:
    """Return a flat list of accessibility elements, optionally filtered.

    ``window_title`` scopes the search to one window by a case-insensitive
    substring of its title — far fewer nodes to walk, and far less ambiguity
    than searching the whole desktop.
    """
    # Only forwarded when actually requested: a backend written before scoping
    # existed keeps working for every call that does not ask for it, and fails
    # loudly at the point someone does.
    extra = {"window_title": window_title} if window_title else {}
    return get_backend().list_elements(
        app_name=app_name, max_results=int(max_results), **extra,
    )


SCAN_LIMIT = 1500


def find_accessibility_elements(name: Optional[str] = None,
                                role: Optional[str] = None,
                                app_name: Optional[str] = None,
                                window_title: Optional[str] = None,
                                contains: bool = False,
                                max_results: int = 50,
                                scan_limit: int = SCAN_LIMIT,
                                ) -> List[AccessibilityElement]:
    """Matching elements, best name match first.

    ``max_results`` caps the **matches returned**; ``scan_limit`` caps how many
    elements are examined to find them. They are separate on purpose — one
    number cannot mean both, and conflating them quietly turns "give me up to
    40 buttons" into "only look at the first 40 elements on the desktop".

    Without ``window_title`` the scan covers the front-most windows up to
    ``scan_limit`` and stops, so a target further back is not found. Name the
    window for a search that is both complete and far faster.

    With ``contains`` the name is matched as a case-insensitive substring and
    the results are ranked so an exact name wins: searching "OK" offers the
    ``OK`` button ahead of ``OK and close``.
    """
    found = [element for element in list_accessibility_elements(
        app_name=app_name, max_results=scan_limit, window_title=window_title)
        if element_matches(element, name=name, role=role, app_name=app_name,
                           contains=contains)]
    if contains and name:
        found = rank_by_name(found, name)
    return found[:max(0, int(max_results))]


def find_accessibility_element(name: Optional[str] = None,
                               role: Optional[str] = None,
                               app_name: Optional[str] = None,
                               window_title: Optional[str] = None,
                               contains: bool = False,
                               ) -> Optional[AccessibilityElement]:
    """First element matching all provided filters, or ``None``."""
    found = find_accessibility_elements(
        name=name, role=role, app_name=app_name, window_title=window_title,
        contains=contains)
    return found[0] if found else None


def click_accessibility_element(name: Optional[str] = None,
                                role: Optional[str] = None,
                                app_name: Optional[str] = None,
                                window_title: Optional[str] = None,
                                contains: bool = False,
                                ) -> bool:
    """Click the center of the first element matching the filters.

    Returns ``True`` on success, ``False`` if nothing matched. Raises
    :class:`AccessibilityNotAvailableError` if the platform backend is
    missing.

    Deliberately moves the real pointer rather than calling the Invoke pattern:
    Invoke does not require the control to be on screen, and so skips the
    hover / focus / drag state an application uses to decide whether a human
    actually clicked it.
    """
    element = find_accessibility_element(
        name=name, role=role, app_name=app_name, window_title=window_title,
        contains=contains,
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


def _scope_kwargs(window_title: Optional[str], contains: bool) -> Dict[str, Any]:
    """The narrowing arguments, omitted entirely when nothing was asked for."""
    extra: Dict[str, Any] = {}
    if window_title:
        extra["window_title"] = window_title
    if contains:
        extra["contains"] = True
    return extra


def control_get_value(name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None,
                      window_title: Optional[str] = None,
                      contains: bool = False) -> Optional[str]:
    """Read a control's value (e.g. a textbox/combo), or None if not found.

    ``window_title`` narrows the search to one window, which disambiguates
    controls that share a name across applications.
    """
    # Forwarded only when asked for, so a backend written before scoping
    # existed keeps working for every call that does not use it.
    extra = _scope_kwargs(window_title, contains)
    return get_backend().get_value(
        name=name, role=role, app_name=app_name, automation_id=automation_id,
        **extra)


def control_get_state(name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None,
                      window_title: Optional[str] = None,
                      contains: bool = False,
                      ) -> Optional[Dict[str, Any]]:
    """Read everything the control currently holds, in one call.

    ``value`` (+ ``read_only``), ``toggle``, ``selected``, ``number`` — only the
    keys the control actually supports, so an absent key means "no such state"
    rather than "empty". This is the half pixels cannot answer: text scrolled
    out of view, a checkbox's true state, a slider's exact number. Password
    fields report only ``{"password": True}``.
    """
    extra = _scope_kwargs(window_title, contains)
    return get_backend().get_state(
        name=name, role=role, app_name=app_name, automation_id=automation_id,
        **extra)


def control_set_value(value: str, name: Optional[str] = None,
                      role: Optional[str] = None, app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> bool:
    """Set a control's value directly (no per-key typing). True on success."""
    return get_backend().set_value(
        value, name=name, role=role, app_name=app_name,
        automation_id=automation_id)


def control_invoke(name: Optional[str] = None, role: Optional[str] = None,
                   app_name: Optional[str] = None,
                   automation_id: Optional[str] = None) -> bool:
    """Invoke a control's default action (e.g. press a button)."""
    return get_backend().invoke(
        name=name, role=role, app_name=app_name, automation_id=automation_id)


def control_toggle(name: Optional[str] = None, role: Optional[str] = None,
                   app_name: Optional[str] = None,
                   automation_id: Optional[str] = None) -> bool:
    """Toggle a control (e.g. a checkbox / switch)."""
    return get_backend().toggle(
        name=name, role=role, app_name=app_name, automation_id=automation_id)


def read_control_table(name: Optional[str] = None, role: Optional[str] = None,
                       app_name: Optional[str] = None,
                       automation_id: Optional[str] = None,
                       ) -> List[List[str]]:
    """Read a grid/table/list control as rows of cell strings."""
    return get_backend().read_table(
        name=name, role=role, app_name=app_name, automation_id=automation_id)


__all__ = [
    "AccessibilityElement", "AccessibilityNotAvailableError",
    "AXTreeNode",
    "click_accessibility_element", "dump_accessibility_tree",
    "find_accessibility_element", "list_accessibility_elements",
    "control_get_value", "control_set_value", "control_invoke",
    "control_toggle", "read_control_table",
]
