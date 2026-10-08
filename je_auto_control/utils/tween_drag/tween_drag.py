"""Eased / tweened interpolated drag along a curved path.

AutoControl has humanized *jitter* but no deterministic named easings.
:func:`tween_points` produces an eased sequence of points between two
coordinates (pure math), and :func:`tween_drag` presses at the start, moves
through the points, and releases at the end — for smooth, deterministic
drags (PyAutoGUI-style ``tween``).

The point math is pure and unit-testable; dispatch goes through an
injectable ``sink`` so the drag is tested without real input. Imports no
``PySide6``.

The press / move / release sequence itself is :func:`_drag_through`, shared
with ``mouse_path.drag_path``: optional pacing (``step_delay_s`` after each
move, ``settle_s`` before the press, after it and before the release) and a
release that runs in ``finally``, at the last point the pointer reached, if
any step raises.
"""
import math
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

Sink = Callable[[Dict[str, Any]], None]


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
    if easing not in _EASINGS:
        # It fell back to linear silently, so a typo ("ease-in-out") hid.
        raise ValueError(f"unknown easing {easing!r}; choose from {easing_names()}")
    curve = _EASINGS[easing]
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


def _pause_seconds(value: Any, name: str) -> float:
    """``value`` as a finite, non-negative number of seconds, else ValueError.

    A NaN would pass a plain ``< 0`` test and then make ``time.sleep`` raise
    with the button already held, so finiteness is checked up front.
    """
    try:
        seconds = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number of seconds, got {value!r}") from error
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")
    return seconds


def _pause(seconds: float) -> None:
    if seconds:
        time.sleep(seconds)


def _release_quietly(dispatch: Sink, button: str, point: Sequence[int]) -> None:
    """Release ``button`` at ``point`` from a ``finally``; never raises.

    An exception here would replace the one that ended the drag, which is
    what the caller needs to see, so a failed release is logged instead.
    ``Exception`` rather than a list: the default sink raises the
    ``AutoControlException`` family, which no builtin type covers.
    """
    try:
        dispatch({"op": "release", "button": button, "x": point[0], "y": point[1]})
    except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: see docstring
        autocontrol_logger.error("failed to release %r after an aborted drag: %r", button, error)


def _drag_through(points: List[List[int]], button: str, dispatch: Sink,
                  step_delay_s: Any = 0.0, settle_s: Any = 0.0) -> None:
    """Press at ``points[0]``, move through every point, release at ``points[-1]``.

    ``settle_s`` (when non-zero) first moves to the start and rests there,
    then rests after the press and again before the release; ``step_delay_s``
    rests after each move. With both at 0 the events are exactly press,
    moves, release. If any step raises, the button is released in
    ``finally`` at the last point the pointer reached -- not at the end,
    which would complete a drop the drag never got to -- and a failing
    cleanup release is logged rather than raised over the original error.
    Both pauses are checked before anything is dispatched.
    """
    step_delay = _pause_seconds(step_delay_s, "step_delay_s")
    settle = _pause_seconds(settle_s, "settle_s")
    first, last = points[0], points[-1]
    if settle:
        dispatch({"op": "move", "x": first[0], "y": first[1]})
        time.sleep(settle)
    dispatch({"op": "press", "button": button, "x": first[0], "y": first[1]})
    reached: Sequence[int] = first
    held = True
    try:
        _pause(settle)
        for x, y in points:
            dispatch({"op": "move", "x": x, "y": y})
            reached = (x, y)
            _pause(step_delay)
        _pause(settle)
        dispatch({"op": "release", "button": button, "x": last[0], "y": last[1]})
        held = False
    finally:
        if held:
            _release_quietly(dispatch, button, reached)


def tween_drag(start: Tuple[int, int], end: Tuple[int, int], *,
               steps: int = 30, easing: str = "ease_in_out_quad",
               button: str = "mouse_left",
               sink: Optional[Sink] = None,
               step_delay_s: float = 0.0, settle_s: float = 0.0,
               ) -> Dict[str, Any]:
    """Drag from ``start`` to ``end`` along an eased path; return point count.

    ``step_delay_s`` rests after each move and ``settle_s`` before the press,
    after it and before the release (seconds, default 0: no pause). Apps
    that tell a drag from a click by the pointer's motion need both. If a
    step raises, the button is released where the pointer stopped.
    """
    points = tween_points(start, end, steps, easing)
    _drag_through(points, button, sink or _default_sink, step_delay_s, settle_s)
    return {"points": len(points), "path": points}
