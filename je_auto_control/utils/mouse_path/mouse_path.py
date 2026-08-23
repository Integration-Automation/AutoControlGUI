"""Multi-waypoint mouse gestures: move or drag through a polyline of points.

``humanize.humanized_path`` and ``tween_drag`` only interpolate a *single*
start -> end hop. Real gestures — signatures, marquee/rubber-band selections,
drag-through-multiple-drop-targets, shape gestures — need an arbitrary chain of
waypoints with the button optionally held down across the whole path.

:func:`plan_path` is pure point math (reusing the named easings from
``tween_drag``) and is unit-testable on its own; :func:`move_along_path` and
:func:`drag_path` dispatch through an injectable ``sink`` so the gesture is
tested without real input. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict, List, Optional, Sequence

from je_auto_control.utils.tween_drag.tween_drag import easing_names, tween_points

Point = Sequence[int]
Sink = Callable[[Dict[str, Any]], None]


def plan_path(waypoints: Sequence[Point], *, easing: str = "linear",
              per_segment_steps: int = 20) -> List[List[int]]:
    """Return the eased point list passing through every waypoint in order.

    Each consecutive pair is interpolated with ``per_segment_steps`` eased steps
    (named easings from ``tween_drag``); shared junction points are not
    duplicated. Fewer than two waypoints yields the points unchanged.
    """
    points: List[List[int]] = []
    if not waypoints:
        return points
    if len(waypoints) == 1:
        first = waypoints[0]
        return [[int(first[0]), int(first[1])]]
    for index in range(len(waypoints) - 1):
        here, there = waypoints[index], waypoints[index + 1]
        segment = tween_points((int(here[0]), int(here[1])),
                               (int(there[0]), int(there[1])),
                               per_segment_steps, easing)
        points.extend(segment[1:] if index else segment)
    return points


def _default_sink(event: Dict[str, Any]) -> None:
    """Default dispatch: drive the real mouse backend."""
    from je_auto_control.wrapper.auto_control_mouse import (
        press_mouse, release_mouse, set_mouse_position)
    x, y = int(event["x"]), int(event["y"])
    set_mouse_position(x, y)
    op = event["op"]
    if op == "press":
        press_mouse(event.get("button", "mouse_left"), x, y)
    elif op == "release":
        release_mouse(event.get("button", "mouse_left"), x, y)


def move_along_path(waypoints: Sequence[Point], *, easing: str = "linear",
                    per_segment_steps: int = 20,
                    sink: Optional[Sink] = None) -> Dict[str, Any]:
    """Move the pointer through ``waypoints`` (no button held)."""
    points = plan_path(waypoints, easing=easing,
                       per_segment_steps=per_segment_steps)
    dispatch = sink or _default_sink
    for x, y in points:
        dispatch({"op": "move", "x": x, "y": y})
    return {"points": len(points), "path": points}


def drag_path(waypoints: Sequence[Point], *, button: str = "mouse_left",
              easing: str = "linear", per_segment_steps: int = 20,
              sink: Optional[Sink] = None) -> Dict[str, Any]:
    """Press at the first waypoint, move through the path, release at the last."""
    points = plan_path(waypoints, easing=easing,
                       per_segment_steps=per_segment_steps)
    if not points:
        return {"points": 0, "path": points}
    dispatch = sink or _default_sink
    first, last = points[0], points[-1]
    dispatch({"op": "press", "button": button, "x": first[0], "y": first[1]})
    for x, y in points:
        dispatch({"op": "move", "x": x, "y": y})
    dispatch({"op": "release", "button": button, "x": last[0], "y": last[1]})
    return {"points": len(points), "path": points}


def path_easings() -> List[str]:
    """Return the available easing names (shared with ``tween_drag``)."""
    return easing_names()
