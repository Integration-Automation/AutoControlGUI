"""Eased / tweened interpolated drag along a curved path.

AutoControl has humanized *jitter* but no deterministic named easings.
:func:`tween_points` produces an eased sequence of points between two
coordinates (pure math), and :func:`tween_drag` presses at the start, moves
through the points, and releases at the end — for smooth, deterministic
drags (PyAutoGUI-style ``tween``).

The point math is pure and unit-testable; dispatch goes through an
injectable ``sink`` so the drag is tested without real input. Imports no
``PySide6``.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple


def _linear(t: float) -> float:
    return t


def _ease_in_out_quad(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 2) / 2


def _ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def _ease_in_cubic(t: float) -> float:
    return t ** 3


_EASINGS: Dict[str, Callable[[float], float]] = {
    "linear": _linear,
    "ease_in_out_quad": _ease_in_out_quad,
    "ease_out_cubic": _ease_out_cubic,
    "ease_in_cubic": _ease_in_cubic,
}


def easing_names() -> List[str]:
    """Return the available easing-function names."""
    return sorted(_EASINGS)


def tween_points(start: Tuple[int, int], end: Tuple[int, int],
                 steps: int = 30,
                 easing: str = "ease_in_out_quad") -> List[List[int]]:
    """Return ``steps + 1`` eased points from ``start`` to ``end``."""
    curve = _EASINGS.get(easing, _linear)
    count = max(1, int(steps))
    start_x, start_y = start
    end_x, end_y = end
    points: List[List[int]] = []
    for index in range(count + 1):
        progress = curve(index / count)
        points.append([round(start_x + (end_x - start_x) * progress),
                       round(start_y + (end_y - start_y) * progress)])
    return points


def _default_sink(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import (
        press_mouse, release_mouse, set_mouse_position)
    x, y = int(event["x"]), int(event["y"])
    op = event["op"]
    if op == "move":
        set_mouse_position(x, y)
    elif op == "press":
        set_mouse_position(x, y)
        press_mouse(event.get("button", "mouse_left"), x, y)
    elif op == "release":
        set_mouse_position(x, y)
        release_mouse(event.get("button", "mouse_left"), x, y)


def tween_drag(start: Tuple[int, int], end: Tuple[int, int], *,
               steps: int = 30, easing: str = "ease_in_out_quad",
               button: str = "mouse_left",
               sink: Optional[Callable[[Dict[str, Any]], None]] = None
               ) -> Dict[str, Any]:
    """Drag from ``start`` to ``end`` along an eased path; return point count."""
    points = tween_points(start, end, steps, easing)
    dispatch = sink or _default_sink
    first, last = points[0], points[-1]
    dispatch({"op": "press", "button": button, "x": first[0], "y": first[1]})
    for x, y in points:
        dispatch({"op": "move", "x": x, "y": y})
    dispatch({"op": "release", "button": button, "x": last[0], "y": last[1]})
    return {"points": len(points), "path": points}
