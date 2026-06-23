"""Classify whether an action actually did anything, with target-local attribution.

After an agent clicks, the crucial question is "did that do anything, and was it the *right*
thing?" — but nothing answers it on the *first* step. ``screen_state.diff_snapshots`` and
``element_diff`` report what changed but never tie the change back to the action; ``loop_guard``
only flags a no-op after the same digest repeats N times (so the agent loops 2-8 times first);
``actionability`` is purely a *pre*-action gate. ``action_effect`` closes the loop: it diffs the
before/after observation, and given the action's target point classifies the result as
``no_op`` (nothing changed), ``changed_near_target`` (the change happened where we acted — a
button depressed), ``changed_elsewhere`` (a surprise dialog popped somewhere else), or
``changed`` (something changed but the action had no point to attribute to).

Pure-stdlib over element dicts + the action record; reuses ``element_diff.match_elements`` for
the overlap join and ``observation_delta``'s field-change check. Fully deterministic and
unit-testable with no device. Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

Element = Dict[str, Any]


@dataclass(frozen=True)
class EffectVerdict:
    """The classified effect of an action plus its attribution evidence."""

    effect: str
    changed_near_target: bool
    changed_count: int
    changed_centers: List[List[int]]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Return the verdict as a plain dict."""
        return asdict(self)


def _center(element: Element) -> List[int]:
    return [int(element.get("x", 0)) + int(element.get("width", 0)) // 2,
            int(element.get("y", 0)) + int(element.get("height", 0)) // 2]


def _action_point(action: Any) -> Optional[List[int]]:
    """Extract the (x, y) the action targets, or ``None`` if it has no coordinate."""
    if not isinstance(action, dict):
        return None
    if "x" in action and "y" in action:
        return [int(action["x"]), int(action["y"])]
    point = action.get("point") or action.get("center")
    return [int(point[0]), int(point[1])] if point else None


def _changed_elements(before: Sequence[Element], after: Sequence[Element],
                      iou_threshold: float, move_threshold: int):
    """Return every element that was added / removed / changed between two frames."""
    from je_auto_control.utils.element_diff import match_elements
    from je_auto_control.utils.observation_delta.observation_delta import (
        _changed_fields)
    diff = match_elements(list(before), list(after), iou_threshold=iou_threshold)
    changed = [pair["after"] for pair in diff["matched"]
               if _changed_fields(pair["before"], pair["after"], move_threshold)]
    return diff["added"] + diff["removed"] + changed


def _near(centers: Sequence[List[int]], point: Sequence[int], radius: int) -> bool:
    return any(abs(cx - point[0]) <= radius and abs(cy - point[1]) <= radius
               for cx, cy in centers)


def classify_effect(before: Sequence[Element], after: Sequence[Element], action: Any,
                    *, radius: int = 64, iou_threshold: float = 0.5,
                    move_threshold: int = 5) -> EffectVerdict:
    """Classify the effect of ``action`` from the before/after observation pair."""
    changed = _changed_elements(before, after, float(iou_threshold),
                                int(move_threshold))
    centers = [_center(element) for element in changed]
    if not changed:
        return EffectVerdict("no_op", False, 0, [],
                             "no element was added, removed or changed")
    point = _action_point(action)
    if point is None:
        return EffectVerdict("changed", False, len(changed), centers,
                             "the screen changed but the action had no target point")
    if _near(centers, point, int(radius)):
        return EffectVerdict("changed_near_target", True, len(changed), centers,
                             "a change occurred within radius of the target point")
    return EffectVerdict("changed_elsewhere", False, len(changed), centers,
                         "the screen changed, but away from the target point")


def effect_near_point(before: Sequence[Element], after: Sequence[Element],
                      point: Sequence[int], *, radius: int = 64,
                      iou_threshold: float = 0.5, move_threshold: int = 5) -> bool:
    """Return whether any change between the frames lies within ``radius`` of ``point``."""
    changed = _changed_elements(before, after, float(iou_threshold),
                                int(move_threshold))
    return _near([_center(element) for element in changed], point, int(radius))


def is_no_op(before: Sequence[Element], after: Sequence[Element], *,
             iou_threshold: float = 0.5, move_threshold: int = 5) -> bool:
    """Return whether the action produced no observable change at all."""
    return not _changed_elements(before, after, float(iou_threshold),
                                 int(move_threshold))
