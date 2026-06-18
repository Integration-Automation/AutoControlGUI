"""Human-like mouse motion: curved, eased Bezier paths with jitter.

The path generation (:func:`humanized_path`) is a pure, deterministic
function — given a seed it always returns the same waypoints — so it can
be unit-tested without touching the OS. :func:`move_mouse_humanized`
walks the generated path through the platform mouse wrapper.
"""
import math
import random
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

Point = Tuple[float, float]


@dataclass
class HumanizedMotion:
    """Tuning for a human-like move.

    ``overshoot`` and ``curve`` are fractions of the travel distance;
    ``jitter`` is a per-waypoint pixel wobble. ``seed`` makes the path
    deterministic (reproducible tests, repeatable demos).
    """
    steps: int = 40
    curve: float = 0.2
    overshoot: float = 0.0
    jitter: float = 1.0
    seed: Optional[int] = None


def _round(value: float) -> int:
    return int(round(value))


def _ease(t: float) -> float:
    """Smoothstep ease-in-out so the cursor accelerates then settles."""
    return t * t * (3.0 - 2.0 * t)


def _cubic_bezier(p0: Point, p1: Point, p2: Point, p3: Point,
                  t: float) -> Point:
    """Cubic Bezier point at parameter ``t`` in [0, 1]."""
    u = 1.0 - t
    x = (u * u * u * p0[0] + 3 * u * u * t * p1[0]
         + 3 * u * t * t * p2[0] + t * t * t * p3[0])
    y = (u * u * u * p0[1] + 3 * u * u * t * p1[1]
         + 3 * u * t * t * p2[1] + t * t * t * p3[1])
    return x, y


def humanized_path(start: Point, end: Point,
                   motion: Optional[HumanizedMotion] = None
                   ) -> List[Tuple[int, int]]:
    """Return integer ``(x, y)`` waypoints from ``start`` to ``end``.

    The path follows an eased cubic Bezier bowed to one side, with
    optional overshoot past the target and per-waypoint jitter. The final
    waypoint is always exactly ``end``. Deterministic when ``motion.seed``
    is set.
    """
    motion = motion or HumanizedMotion()
    rng = random.Random(motion.seed)  # nosec B311  # reason: non-crypto motion jitter
    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    dx, dy = ex - sx, ey - sy
    dist = math.hypot(dx, dy)
    if dist == 0.0:
        return [(_round(ex), _round(ey))]
    perp_x, perp_y = -dy / dist, dx / dist
    bow = motion.curve * dist * rng.uniform(-1.0, 1.0)
    unit_x, unit_y = dx / dist, dy / dist
    aim_x = ex + unit_x * motion.overshoot * dist
    aim_y = ey + unit_y * motion.overshoot * dist
    control1 = (sx + dx * 0.33 + perp_x * bow, sy + dy * 0.33 + perp_y * bow)
    control2 = (sx + dx * 0.66 + perp_x * bow, sy + dy * 0.66 + perp_y * bow)
    steps = max(2, int(motion.steps))
    points: List[Tuple[int, int]] = []
    for index in range(1, steps + 1):
        t = _ease(index / steps)
        bx, by = _cubic_bezier((sx, sy), control1, control2,
                               (aim_x, aim_y), t)
        if index < steps:
            bx += rng.uniform(-motion.jitter, motion.jitter)
            by += rng.uniform(-motion.jitter, motion.jitter)
        points.append((_round(bx), _round(by)))
    if motion.overshoot:
        points.append((_round(ex), _round(ey)))
    else:
        points[-1] = (_round(ex), _round(ey))
    return points


def move_mouse_humanized(x: int, y: int, *, duration_s: float = 0.4,
                         motion: Optional[HumanizedMotion] = None,
                         sleep: Callable[[float], None] = time.sleep
                         ) -> List[Tuple[int, int]]:
    """Move the cursor to ``(x, y)`` along a human-like path.

    Returns the integer waypoints walked. ``sleep`` is injectable so tests
    can run without real delays.
    """
    from je_auto_control.wrapper.auto_control_mouse import (
        get_mouse_position, set_mouse_position,
    )
    motion = motion or HumanizedMotion()
    start = get_mouse_position()
    path = humanized_path(start, (x, y), motion)
    per_step = max(0.0, float(duration_s)) / max(1, len(path))
    for point_x, point_y in path:
        set_mouse_position(int(point_x), int(point_y))
        if per_step:
            sleep(per_step)
    return path
