"""Token-budgeted, indexed a11y text observation — what to feed a VLM/agent.

``screen_state.describe_screen`` returns role *counts* plus a flat list of control
labels — but no stable per-element index, no ``[12] button "Submit" @(x,y)`` lines, no
viewport clipping, and no element cap / token budget. Modern desktop/web agents feed a
*flattened, indexed, viewport-pruned* text block (the "accessibility tree as the text
observation" pattern), then act by index ("click [12]"). This builds that observation
and the index behind it, pairing with :doc:`element_parse` and ``set_of_marks``.

Pure-stdlib over plain element dicts (``role`` / ``name`` / ``x`` / ``y`` / ``width`` /
``height``, optionally nested ``children``), so it is fully unit-testable. Imports no
``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

Element = Dict[str, Any]
_INTERACTIVE = {"button", "link", "textbox", "edit", "textfield", "checkbox",
                "radio", "menuitem", "tab", "combobox", "listitem", "switch",
                "slider", "menu", "option"}


def _center(element: Element) -> List[int]:
    return [int(element.get("x", 0)) + int(element.get("width", 0)) // 2,
            int(element.get("y", 0)) + int(element.get("height", 0)) // 2]


def flatten_tree(elements: Sequence[Element], *,
                 interactive_only: bool = True) -> List[Element]:
    """Flatten a (possibly nested ``children``) element tree to a flat list.

    With ``interactive_only`` (default) only actionable roles (button, link, textbox,
    …) survive. Each returned node drops its ``children`` key.
    """
    flat: List[Element] = []

    def walk(items: Sequence[Element]) -> None:
        for element in items:
            flat.append({key: value for key, value in element.items()
                         if key != "children"})
            if element.get("children"):
                walk(element["children"])

    walk(elements)
    if interactive_only:
        flat = [e for e in flat if str(e.get("role", "")).lower() in _INTERACTIVE]
    return flat


def _in_viewport(element: Element, viewport: Optional[Sequence[int]]) -> bool:
    if not viewport:
        return True
    vx, vy, vw, vh = (int(v) for v in viewport[:4])
    cx, cy = _center(element)
    return vx <= cx <= vx + vw and vy <= cy <= vy + vh


def observation_index(elements: Sequence[Element], *,
                      viewport: Optional[Sequence[int]] = None,
                      max_elements: int = 80,
                      interactive_only: bool = True) -> List[Element]:
    """Return the on-screen elements in reading order, capped, each with an ``index``.

    Flattens the tree, keeps only elements whose centre is inside ``viewport`` (if
    given), orders them top-to-bottom / left-to-right, caps at ``max_elements`` and
    assigns a stable ``index`` an agent can refer to.
    """
    from je_auto_control.utils.element_parse import reading_order
    flat = flatten_tree(elements, interactive_only=interactive_only)
    visible = [e for e in flat if _in_viewport(e, viewport)]
    ordered = reading_order(visible)[:int(max_elements)]
    return [dict(element, index=index) for index, element in enumerate(ordered)]


def serialize_observation(elements: Sequence[Element], *,
                          viewport: Optional[Sequence[int]] = None,
                          max_elements: int = 80,
                          interactive_only: bool = True) -> str:
    """Render the indexed observation as ``[i] role "name" @(cx,cy)`` lines."""
    lines = []
    for element in observation_index(elements, viewport=viewport,
                                     max_elements=max_elements,
                                     interactive_only=interactive_only):
        cx, cy = _center(element)
        lines.append(f'[{element["index"]}] {element.get("role", "element")} '
                     f'"{element.get("name", "")}" @({cx},{cy})')
    return "\n".join(lines)
