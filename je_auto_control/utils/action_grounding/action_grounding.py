"""Pre-action grounding guard — reject out-of-bounds clicks, snap near-misses.

``guardrail`` scans text for prompt-injection and ``loop_guard`` detects stuck loops —
but neither validates a *coordinate action* before it is dispatched. An agent loop
executes whatever the model returns with no bounds or target check, so a hallucinated
``(9999, -5)`` click fires into nothing and a 5-pixel-off click misses the button. This
adds the "detect misaligned actions before execution" guard: reject clicks outside the
screen and snap a near-miss coordinate onto the nearest known element's centre.

Pure-stdlib geometry over plain element dicts (``x`` / ``y`` / ``width`` / ``height``),
so it is fully unit-testable. Imports no ``PySide6``.
"""
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

Element = Dict[str, Any]


def in_bounds(x: int, y: int, screen_size: Sequence[int]) -> bool:
    """Whether ``(x, y)`` lies within the ``(width, height)`` screen."""
    width, height = int(screen_size[0]), int(screen_size[1])
    return 0 <= int(x) < width and 0 <= int(y) < height


def _center(element: Element) -> List[int]:
    return [int(element["x"]) + int(element["width"]) // 2,
            int(element["y"]) + int(element["height"]) // 2]


def _contains(element: Element, x: int, y: int) -> bool:
    return (int(element["x"]) <= x < int(element["x"]) + int(element["width"])
            and int(element["y"]) <= y < int(element["y"]) + int(element["height"]))


def snap_to_element(x: int, y: int, elements: Sequence[Element], *,
                    max_dist: float = 8.0) -> Optional[List[int]]:
    """Return the centre of the element at / nearest to ``(x, y)`` (or ``None``).

    A point inside an element snaps to that element's centre; otherwise the nearest
    element centre within ``max_dist`` pixels is returned, else ``None``.
    """
    px, py = int(x), int(y)
    for element in elements:
        if _contains(element, px, py):
            return _center(element)
    best: Optional[List[int]] = None
    best_dist = float("inf")
    for element in elements:
        cx, cy = _center(element)
        dist = math.hypot(cx - px, cy - py)
        if dist < best_dist:
            best_dist, best = dist, [cx, cy]
    return best if best is not None and best_dist <= float(max_dist) else None


def validate_action(action: Mapping[str, Any], *, screen_size: Sequence[int],
                    targets: Optional[Sequence[Element]] = None) -> Dict[str, Any]:
    """Validate a canonical action before dispatch; optionally snap to a target.

    Returns ``{ok, reason, snapped}``. A coordinate outside ``screen_size`` is
    rejected (``ok=False``); when ``targets`` are given, a near-miss coordinate is
    snapped onto the nearest element's centre (``snapped=[x, y]``). Actions without a
    coordinate always pass.
    """
    x, y = action.get("x"), action.get("y")
    if x is None or y is None:
        return {"ok": True, "reason": "no coordinate", "snapped": None}
    if not in_bounds(x, y, screen_size):
        return {"ok": False, "reason": "out of bounds", "snapped": None}
    if targets:
        snapped = snap_to_element(x, y, targets)
        if snapped is not None:
            return {"ok": True, "reason": "snapped", "snapped": snapped}
    return {"ok": True, "reason": "in bounds", "snapped": None}
