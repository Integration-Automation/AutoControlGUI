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


def _pick_position(bbox: Sequence[int], label_w: int, label_h: int,
                   bounds: Optional[Tuple[int, int]],
                   placed: List[Rect]) -> Rect:
    """Pick the first candidate that is in bounds and clears placed labels."""
    fallback: Optional[Rect] = None
    for cx, cy in _candidates(bbox, label_w, label_h):
        rect = (cx, cy, label_w, label_h)
        if fallback is None:
            fallback = rect
        if bounds is not None and not _in_bounds(rect, bounds):
            continue
        if any(_overlap(rect, other) for other in placed):
            continue
        return rect
    if bounds is not None and fallback is not None:
        return _clamp_to_bounds(fallback, bounds)
    return fallback if fallback is not None else (0, 0, label_w, label_h)


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
        bbox = [int(value) for value in mark["bbox"][:4]]
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
