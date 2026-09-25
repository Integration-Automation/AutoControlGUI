"""Place Set-of-Marks labels so they don't overlap, with readable label colours.

Set-of-Marks overlays a numbered label on every element so a vision model can
say "click 7". ``set_of_marks`` draws each label at a fixed offset, so on dense
UIs the numbers pile on top of each other (unreadable) and a dark label on a
dark element vanishes. ``marks_layout`` fixes both with pure geometry:

* :func:`place_labels` — greedy non-overlap placement: for each mark, try a ring
  of candidate positions around its box and take the first that stays in bounds
  and clears every already-placed label.
* :func:`label_color` — pick the label text colour (black or white) with the
  better WCAG contrast against the element's background.

Pure standard library; reuses :func:`a11y_audit.contrast_ratio`. Fully testable
without rendering. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.accessibility.element import element_box

Rect = Tuple[int, int, int, int]

_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)


def _overlap(first: Rect, second: Rect) -> bool:
    """Whether two ``(x, y, w, h)`` rectangles overlap (pure)."""
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return not (ax + aw <= bx or bx + bw <= ax
                or ay + ah <= by or by + bh <= ay)


def _in_bounds(rect: Rect, bounds: Tuple[int, int]) -> bool:
    """Whether ``rect`` fits inside ``(width, height)`` (pure)."""
    x, y, w, h = rect
    return x >= 0 and y >= 0 and x + w <= int(bounds[0]) \
        and y + h <= int(bounds[1])


def _candidates(bbox: Sequence[int], label_w: int,
                label_h: int) -> List[Tuple[int, int]]:
    """Candidate label top-left positions around an anchor box (pure)."""
    bx, by, bw, bh = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
    right = bx + bw - label_w
    below = by + bh
    return [
        (bx, by - label_h),      # above, left-aligned (default SoM spot)
        (right, by - label_h),   # above, right-aligned
        (bx, below),             # below, left-aligned
        (right, below),          # below, right-aligned
        (bx, by),                # inside, top-left
        (right, by),             # inside, top-right
    ]


def _clamp_to_bounds(rect: Rect, bounds: Tuple[int, int]) -> Rect:
    """Shift ``rect`` to fit inside ``(width, height)`` (pure fallback)."""
    x, y, w, h = rect
    x = max(0, min(int(bounds[0]) - w, x))
    y = max(0, min(int(bounds[1]) - h, y))
    return (x, y, w, h)


def _allowed(rect: Rect, floor: Tuple[int, int], bounds: Optional[Tuple[int, int]]) -> bool:
    """Whether ``rect`` is at or past ``floor`` and, when given, inside ``bounds``."""
    if rect[0] < floor[0] or rect[1] < floor[1]:
        return False
    return bounds is None or _in_bounds(rect, bounds)


def _pick_position(bbox: Sequence[int], label_w: int, label_h: int,
                   bounds: Optional[Tuple[int, int]],
                   placed: List[Rect]) -> Rect:
    """Pick the first candidate that is in bounds and clears placed labels.

    Labels go below 0 only where their mark does: without bounds a mark at
    y=0 got its label at y=-16, but a mark on a monitor left of or above the
    primary one had its label clamped to 0, up to 1,500 px away.
    """
    floor = (min(0, bbox[0]), min(0, bbox[1]))
    if bounds is not None and not _in_bounds((bbox[0], bbox[1], 1, 1), bounds):
        bounds = None                # the mark itself is outside: keep the label beside it
    fallback: Optional[Rect] = None
    for cx, cy in _candidates(bbox, label_w, label_h):
        rect = (cx, cy, label_w, label_h)
        if fallback is None:
            fallback = rect
        if not _allowed(rect, floor, bounds):
            continue
        if any(_overlap(rect, other) for other in placed):
            continue
        return rect
    start = fallback if fallback is not None else (0, 0, label_w, label_h)
    return _free_spot(start, floor, bounds, placed)


def _ring(radius: int) -> List[Tuple[int, int]]:
    """Grid steps at Chebyshev distance ``radius`` from the origin, nearest first."""
    steps = [(dx, dy) for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)
             if max(abs(dx), abs(dy)) == radius]
    return sorted(steps, key=lambda step: (abs(step[0]) + abs(step[1]), step[1], step[0]))


def _free_spot(rect: Rect, floor: Tuple[int, int], bounds: Optional[Tuple[int, int]],
               placed: List[Rect]) -> Rect:
    """The nearest label-sized step from ``rect``, in any direction, that is free and allowed.

    The fallback only stepped down and then right: past the right edge it
    returned the same out-of-bounds rect for every remaining mark, 1,000 px
    from them and on top of each other.
    """
    x, y, w, h = rect
    x, y = max(floor[0], x), max(floor[1], y)
    if bounds is not None:
        x, y, w, h = _clamp_to_bounds((x, y, w, h), bounds)
    for radius in range(_MAX_RINGS + 1):
        for dx, dy in _ring(radius):
            candidate = (x + dx * w, y + dy * h, w, h)
            if _allowed(candidate, floor, bounds) and \
                    not any(_overlap(candidate, other) for other in placed):
                return candidate
    return (x, y, w, h)


_MAX_RINGS = 16


def place_labels(marks: Sequence[Dict[str, Any]], *, label_width: int = 22,
                 label_height: int = 16,
                 bounds: Optional[Sequence[int]] = None
                 ) -> List[Dict[str, Any]]:
    """Lay out non-overlapping label boxes for ``marks`` (pure).

    ``marks`` is the :func:`set_of_marks.mark_elements` output (each has an
    ``id`` and ``bbox`` ``[x, y, w, h]``). ``bounds`` is the ``(width, height)``
    the labels must stay within. Returns ``[{id, label, anchor}]`` where
    ``label`` is the placed ``[x, y, w, h]`` box.
    """
    size = (int(label_width), int(label_height))
    limit = (int(bounds[0]), int(bounds[1])) if bounds else None
    placed: List[Rect] = []
    results: List[Dict[str, Any]] = []
    for mark in marks:
        box = element_box(mark)
        if box is None:
            # {bounds: ...} and {x, y, width, height} marks raised KeyError('bbox').
            raise ValueError(f"mark {mark.get('id')!r} has no bbox, bounds or x/y/width/height")
        bbox = list(box)
        rect = _pick_position(bbox, size[0], size[1], limit, placed)
        placed.append(rect)
        results.append({"id": mark.get("id"), "label": list(rect),
                        "anchor": [bbox[0], bbox[1]]})
    return results


def label_color(background: Sequence[float]) -> Dict[str, Any]:
    """Pick the higher-contrast label text colour for ``background`` (pure).

    Returns ``{rgb, contrast}`` — black or white, whichever has the better WCAG
    contrast ratio against the element background colour.
    """
    from je_auto_control.utils.a11y_audit import contrast_ratio
    black_contrast = contrast_ratio(background, _BLACK)
    white_contrast = contrast_ratio(background, _WHITE)
    if white_contrast >= black_contrast:
        return {"rgb": list(_WHITE), "contrast": round(white_contrast, 3)}
    return {"rgb": list(_BLACK), "contrast": round(black_contrast, 3)}
