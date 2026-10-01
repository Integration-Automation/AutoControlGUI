"""Keyboard focus order: expected Tab sequence, a WCAG audit, and set-focus.

Nothing in the toolkit reasons about *keyboard* navigation. ``focus_order`` adds:

* :func:`is_interactive_role` — is a role one that normally takes keyboard focus,
* :func:`tab_order` — the focusable elements in the order ``Tab`` will visit them
  (their reading order: top-to-bottom, left-to-right),
* :func:`audit_focus_order` — a WCAG 2.4.x focus-order report over a flat element
  list (the sequence plus flagged problems, e.g. a focusable element with no
  visible area),
* :func:`focus_control` — set the keyboard focus on a control (device action).

The first three are pure functions over :class:`AccessibilityElement` lists —
``tab_order`` reuses :func:`element_parse.reading_order` for row banding and
``is_interactive_role`` reuses :func:`ax_tree_walk.humanize_role`, so no logic is
duplicated. ``focus_control`` is a thin dispatch onto the injectable
``accessibility.backends.get_backend()`` seam; the real ``SetFocus`` call lives in
the Windows backend. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence, Union

from je_auto_control.utils.accessibility.element import AccessibilityElement
from je_auto_control.utils.ax_tree_walk import humanize_role
from je_auto_control.utils.element_parse import reading_order

# Roles that conventionally take keyboard focus, as lower-case keys with
# spaces removed: UIA ("CheckBox"), AT-SPI ("push button", what the Linux
# backend reports), macOS AX with its prefix dropped ("AXTextField") and ARIA.
# Only the UIA names were known, so Linux and macOS trees had no tab order.
_INTERACTIVE_KEYS = frozenset({
    # UIA
    "button", "calendar", "checkbox", "combobox", "edit", "hyperlink",
    "listitem", "menuitem", "radiobutton", "scrollbar", "slider", "spinner",
    "splitbutton", "tab", "tabitem", "treeitem", "dataitem", "thumb",
    # AT-SPI
    "pushbutton", "togglebutton", "entry", "passwordtext", "spinbutton",
    "pagetab", "checkmenuitem", "radiomenuitem", "link",
    # macOS AX
    "textfield", "textarea", "popupbutton", "menubutton", "incrementor",
    "disclosuretriangle",
    # ARIA
    "textbox", "searchbox", "radio", "switch", "option", "menu", "menuitemcheckbox",
    "menuitemradio",
})


def _role_key(role: Union[str, int]) -> str:
    """``role`` as a lookup key: humanized, AX prefix dropped, lower case, no spaces."""
    text = humanize_role(role)
    if text.startswith("AX") and text[2:3].isupper():
        text = text[2:]
    return "".join(text.lower().split()).replace("_", "")


def is_interactive_role(role: Union[str, int]) -> bool:
    """Return True if ``role`` is one that normally accepts keyboard focus (any platform's spelling)."""
    return _role_key(role) in _INTERACTIVE_KEYS


def _box(element: AccessibilityElement, index: int) -> Dict[str, Any]:
    left, top, width, height = element.bounds
    return {"x": left, "y": top, "width": width, "height": height, "_idx": index}


def tab_order(elements: Sequence[AccessibilityElement], *,
              row_tol: int = 12) -> List[AccessibilityElement]:
    """Return the focusable elements in the order ``Tab`` would visit them.

    Filters to enabled elements of an :func:`is_interactive_role` role, then
    orders by reading order (rows within ``row_tol`` px share a row, ordered
    left-to-right). A disabled control is skipped, as ``Tab`` skips it.
    """
    interactive = [el for el in elements if el.enabled and is_interactive_role(el.role)]
    boxes = [_box(el, index) for index, el in enumerate(interactive)]
    ordered = reading_order(boxes, row_tol=int(row_tol))
    return [interactive[box["_idx"]] for box in ordered]


def audit_focus_order(elements: Sequence[AccessibilityElement], *,
                      row_tol: int = 12) -> Dict[str, Any]:
    """Return a WCAG 2.4.x focus-order report over a flat element list.

    ``order`` is the expected Tab sequence (``tab_index`` / ``name`` / ``role`` /
    ``bounds``); ``issues`` flags focusable elements with no visible area
    (WCAG 2.4.7 Focus Visible — focus would land somewhere unseen).
    """
    order = tab_order(elements, row_tol=row_tol)
    sequence: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    for tab_index, element in enumerate(order):
        role = humanize_role(element.role)
        _left, _top, width, height = element.bounds
        sequence.append({"tab_index": tab_index, "name": element.name,
                         "role": role, "bounds": list(element.bounds)})
        if width <= 0 or height <= 0:
            issues.append({"tab_index": tab_index, "name": element.name,
                           "role": role, "issue": "zero_area_focusable",
                           "wcag": "2.4.7 Focus Visible"})
    return {"order": sequence, "issues": issues,
            "focusable_count": len(order), "issue_count": len(issues)}


def focus_control(name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> bool:
    """Set keyboard focus on the matched control (UIA SetFocus); True on success."""
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend().set_focus(name=name, role=role, app_name=app_name,
                                   automation_id=automation_id)
