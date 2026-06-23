"""Token-budgeted "what changed since last step" observation delta.

``observation.serialize_observation`` renders *one full frame* of the UI — feeding it to a
model every turn blows the very token budget that module was built to respect, and forces the
model to re-read the whole screen to spot the one new dialog. ``element_diff`` gives the
stable-ID correspondence between two frames but stops at matched/added/removed *element pairs*
— it does not render a compact, indexed, budget-capped delta the model can act on.

This is the missing serializer: it diffs the previous and current observation, classifies each
matched element as *changed* (role / name / enabled / moved) or *stable*, and renders only the
churn as ``+ [i] role "name"`` (appeared) / ``- role "name"`` (vanished) / ``~ [i] role "name"``
(changed) lines — added and changed first, stable dropped — capped at ``max_lines``. The model
sees "what changed" instead of the whole screen again.

Pure-stdlib over element dicts; reuses ``element_diff.match_elements`` for the overlap join and
``observation.observation_index`` for reading-order indexing. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

Element = Dict[str, Any]
_CHANGE_KEYS = ("role", "name", "enabled", "value")


def _center(element: Element) -> List[int]:
    return [int(element.get("x", 0)) + int(element.get("width", 0)) // 2,
            int(element.get("y", 0)) + int(element.get("height", 0)) // 2]


def _changed_fields(before: Element, after: Element, move_threshold: int) -> List[str]:
    """Return the attribute names that differ between two matched elements."""
    fields = [key for key in _CHANGE_KEYS if before.get(key) != after.get(key)]
    bx, by = _center(before)
    ax, ay = _center(after)
    if abs(ax - bx) > move_threshold or abs(ay - by) > move_threshold:
        fields.append("moved")
    return fields


def delta_index(prev: Sequence[Element], curr: Sequence[Element], *,
                iou_threshold: float = 0.5,
                move_threshold: int = 5) -> Dict[str, List[Any]]:
    """Diff two element lists into ``{added, removed, changed, stable}``.

    ``changed`` items are ``{"after", "fields"}`` (the differing attribute names);
    ``added`` / ``removed`` / ``stable`` are element lists. Matching is by IoU overlap.
    """
    from je_auto_control.utils.element_diff import match_elements
    result = match_elements(list(prev), list(curr), iou_threshold=float(iou_threshold))
    changed, stable = [], []
    for pair in result["matched"]:
        fields = _changed_fields(pair["before"], pair["after"], int(move_threshold))
        if fields:
            changed.append({"after": pair["after"], "fields": fields})
        else:
            stable.append(pair["after"])
    return {"added": result["added"], "removed": result["removed"],
            "changed": changed, "stable": stable}


def _line(prefix: str, element: Element, suffix: str = "") -> str:
    cx, cy = _center(element)
    index = element.get("index")
    marker = f"[{index}] " if index is not None else ""
    return (f'{prefix} {marker}{element.get("role", "element")} '
            f'"{element.get("name", "")}" @({cx},{cy}){suffix}')


def summarize_delta(delta: Dict[str, List[Any]], *, max_lines: int = 40) -> str:
    """Render a ``delta_index`` result as budget-capped ``+`` / ``~`` / ``-`` lines.

    Added and changed elements come first (most actionable), then removed; stable
    elements are omitted. Overflow past ``max_lines`` is summarised as ``… (+N more)``.
    """
    lines = [_line("+", element) for element in delta["added"]]
    lines += [_line("~", item["after"], f' ({"/".join(item["fields"])})')
              for item in delta["changed"]]
    lines += [_line("-", element) for element in delta["removed"]]
    if len(lines) > max_lines:
        hidden = len(lines) - max_lines
        lines = lines[:max_lines] + [f"… (+{hidden} more)"]
    return "\n".join(lines)


def delta_observation(prev: Sequence[Element], curr: Sequence[Element], *,
                      viewport: Optional[Sequence[int]] = None,
                      max_elements: int = 80, interactive_only: bool = True,
                      iou_threshold: float = 0.5, move_threshold: int = 5,
                      max_lines: int = 40) -> str:
    """Index both frames, diff them and render the budget-capped change summary."""
    from je_auto_control.utils.observation import observation_index
    prev_idx = observation_index(prev, viewport=viewport, max_elements=max_elements,
                                 interactive_only=interactive_only)
    curr_idx = observation_index(curr, viewport=viewport, max_elements=max_elements,
                                 interactive_only=interactive_only)
    delta = delta_index(prev_idx, curr_idx, iou_threshold=iou_threshold,
                        move_threshold=move_threshold)
    return summarize_delta(delta, max_lines=max_lines)
