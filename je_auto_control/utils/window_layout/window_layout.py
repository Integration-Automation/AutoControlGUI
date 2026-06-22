"""Window tiling/layout geometry planner — halves, quadrants, grids, cascade.

``save_window_layout`` / ``restore_window_layout`` capture and replay the *exact*
positions a user already arranged; nothing *computes* new ones. This is a pure-
geometry planner: given a screen work area it returns the target rectangles for the
common tiling layouts (left/right/top/bottom halves, quadrants, thirds, an R×C grid,
a staggered cascade) so a script can arrange application windows deterministically.

The result is plain geometry that composes with any window-move backend; the planner
itself is cross-platform and has no device dependency, so it is fully unit-testable.
Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

Screen = Sequence[int]
Size = Optional[Sequence[int]]

# slot name -> (x_fraction, y_fraction, width_fraction, height_fraction)
_THIRD = 1.0 / 3.0
_SLOTS: Dict[str, Tuple[float, float, float, float]] = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "left": (0.0, 0.0, 0.5, 1.0),
    "right": (0.5, 0.0, 0.5, 1.0),
    "top": (0.0, 0.0, 1.0, 0.5),
    "bottom": (0.0, 0.5, 1.0, 0.5),
    "top_left": (0.0, 0.0, 0.5, 0.5),
    "top_right": (0.5, 0.0, 0.5, 0.5),
    "bottom_left": (0.0, 0.5, 0.5, 0.5),
    "bottom_right": (0.5, 0.5, 0.5, 0.5),
    "center": (0.25, 0.25, 0.5, 0.5),
    "left_third": (0.0, 0.0, _THIRD, 1.0),
    "center_third": (_THIRD, 0.0, _THIRD, 1.0),
    "right_third": (2.0 * _THIRD, 0.0, _THIRD, 1.0),
}


@dataclass(frozen=True)
class WindowRect:
    """A target window geometry: top-left ``(x, y)`` and ``width`` / ``height``."""

    x: int
    y: int
    width: int
    height: int

    def as_tuple(self) -> Tuple[int, int, int, int]:
        """Return ``(x, y, width, height)`` — ready for a window-move call."""
        return (self.x, self.y, self.width, self.height)

    def to_dict(self) -> Dict[str, int]:
        """Return the rectangle as a plain dict."""
        return asdict(self)


def available_slots() -> List[str]:
    """Return the names of the supported single-window slots."""
    return list(_SLOTS)


def _apply_gap(x: int, y: int, width: int, height: int,
               gap: int) -> Tuple[int, int, int, int]:
    """Inset a rectangle by ``gap`` on every side (min size 1)."""
    return (x + gap, y + gap, max(1, width - 2 * gap), max(1, height - 2 * gap))


def tile_rect(screen: Screen, slot: str, *, gap: int = 0) -> WindowRect:
    """Return the rectangle for a named ``slot`` of the ``screen`` work area.

    ``screen`` is ``(x, y, width, height)``. ``slot`` is one of
    :func:`available_slots` (``left``, ``top_right``, ``center``, ``left_third`` …).
    ``gap`` insets the result on all sides for a margin between tiled windows.
    """
    if slot not in _SLOTS:
        raise ValueError(f"unknown slot: {slot!r}")
    screen_x, screen_y, screen_w, screen_h = (int(value) for value in screen[:4])
    fx, fy, fw, fh = _SLOTS[slot]
    rect = _apply_gap(screen_x + round(fx * screen_w),
                      screen_y + round(fy * screen_h),
                      round(fw * screen_w), round(fh * screen_h), int(gap))
    return WindowRect(*rect)


def grid_rects(screen: Screen, rows: int, cols: int, *,
               gap: int = 0) -> List[WindowRect]:
    """Return one rectangle per cell of an ``rows`` × ``cols`` grid, row-major.

    Splits the ``screen`` work area into equal cells; ``gap`` insets each cell for
    uniform spacing. Raises ``ValueError`` if ``rows`` or ``cols`` is below 1.
    """
    rows, cols = int(rows), int(cols)
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be >= 1")
    screen_x, screen_y, screen_w, screen_h = (int(value) for value in screen[:4])
    cell_w, cell_h = screen_w / cols, screen_h / rows
    rects: List[WindowRect] = []
    for row in range(rows):
        for col in range(cols):
            rect = _apply_gap(screen_x + round(col * cell_w),
                              screen_y + round(row * cell_h),
                              round(cell_w), round(cell_h), int(gap))
            rects.append(WindowRect(*rect))
    return rects


def cascade_rects(screen: Screen, count: int, *, offset: int = 30,
                  size: Size = None) -> List[WindowRect]:
    """Return ``count`` staggered, overlapping rectangles (a window cascade).

    Each window is ``offset`` pixels down-right of the previous one, clamped to stay
    within the ``screen`` work area; ``size`` defaults to 60% of the work area.
    """
    count = int(count)
    if count < 1:
        raise ValueError("count must be >= 1")
    screen_x, screen_y, screen_w, screen_h = (int(value) for value in screen[:4])
    if size is not None:
        win_w, win_h = int(size[0]), int(size[1])
    else:
        win_w, win_h = round(screen_w * 0.6), round(screen_h * 0.6)
    max_x, max_y = screen_x + screen_w - win_w, screen_y + screen_h - win_h
    rects: List[WindowRect] = []
    for index in range(count):
        pos_x = min(screen_x + index * int(offset), max_x)
        pos_y = min(screen_y + index * int(offset), max_y)
        rects.append(WindowRect(int(pos_x), int(pos_y), int(win_w), int(win_h)))
    return rects
