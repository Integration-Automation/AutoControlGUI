"""Coarse labelled cell grid over the screen (or a region).

Vision / VLM grounding works far better when the model can refer to a *coarse cell*
("click cell C3") than to raw pixel coordinates it tends to hallucinate, and a labelled
grid is the standard way to describe a screenshot to such a model and to map its answer
back to a point. The framework had no such helper. This lays an ``rows x cols`` grid over
the screen (or a sub-``region``), labels each cell spreadsheet-style (column letter + row
number, ``A1`` top-left) and converts both ways: point -> containing cell, and cell ->
centre point (ready to click).

Pure-stdlib geometry; the only device-bound path is the default that grabs the live screen
size when neither ``region`` nor ``screen_size`` is given, so every function is fully
unit-testable by passing an explicit region. Imports no ``PySide6``.
"""
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

_LABEL_RE = re.compile(r"([A-Za-z]+)(\d+)")


@dataclass(frozen=True)
class GridCell:
    """One grid cell: spreadsheet ``label``, 0-based ``row`` / ``col`` and bounds."""

    label: str
    row: int
    col: int
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> List[int]:
        """The cell's centre point ``[x, y]`` (ready to click)."""
        return [(self.left + self.right) // 2, (self.top + self.bottom) // 2]

    def to_dict(self) -> Dict[str, Any]:
        """Return the cell as a plain dict including the centre point."""
        data = asdict(self)
        data["center"] = self.center
        return data


def _col_label(index: int) -> str:
    """0-based column index -> spreadsheet letters (0 -> 'A', 26 -> 'AA')."""
    label, number = "", index + 1
    while number > 0:
        number, remainder = divmod(number - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def _col_index(letters: str) -> int:
    """Spreadsheet letters -> 0-based column index ('A' -> 0, 'AA' -> 26)."""
    number = 0
    for char in letters.upper():
        number = number * 26 + (ord(char) - ord("A") + 1)
    return number - 1


def _bounds(region: Optional[Sequence[int]],
            screen_size: Optional[Sequence[int]]) -> Tuple[int, int, int, int]:
    """Resolve the grid rectangle from ``region`` / ``screen_size`` / live screen."""
    if region is not None:
        left, top, right, bottom = (int(v) for v in region)
        return left, top, right, bottom
    if screen_size is not None:
        width, height = (int(v) for v in screen_size)
        return 0, 0, width, height
    from je_auto_control.wrapper.auto_control_screen import screen_size as _live
    width, height = _live()
    return 0, 0, int(width), int(height)


def _edges(start: int, length: int, count: int) -> List[int]:
    """Return ``count`` + 1 evenly spaced integer edges starting at ``start``."""
    return [start + round(i * length / count) for i in range(count + 1)]


def _validate(rows: int, cols: int) -> Tuple[int, int]:
    """Coerce and check the grid shape; both dimensions must be >= 1."""
    rows, cols = int(rows), int(cols)
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must both be >= 1")
    return rows, cols


def _make_cell(row: int, col: int, xs: List[int], ys: List[int]) -> GridCell:
    """Build a ``GridCell`` from a row/col and the precomputed edge arrays."""
    return GridCell(f"{_col_label(col)}{row + 1}", row, col,
                    xs[col], ys[row], xs[col + 1], ys[row + 1])


def grid_cells(rows: int, cols: int, *, region: Optional[Sequence[int]] = None,
               screen_size: Optional[Sequence[int]] = None) -> List[GridCell]:
    """Return every cell of an ``rows`` x ``cols`` grid over the region, row-major."""
    rows, cols = _validate(rows, cols)
    left, top, right, bottom = _bounds(region, screen_size)
    xs = _edges(left, right - left, cols)
    ys = _edges(top, bottom - top, rows)
    return [_make_cell(row, col, xs, ys)
            for row in range(rows) for col in range(cols)]


def cell_for_point(x: int, y: int, rows: int, cols: int, *,
                   region: Optional[Sequence[int]] = None,
                   screen_size: Optional[Sequence[int]] = None
                   ) -> Optional[GridCell]:
    """Return the cell containing ``(x, y)``, or ``None`` if outside the region."""
    rows, cols = _validate(rows, cols)
    left, top, right, bottom = _bounds(region, screen_size)
    if not (left <= x < right and top <= y < bottom):
        return None
    col = min(cols - 1, int((x - left) * cols / (right - left)))
    row = min(rows - 1, int((y - top) * rows / (bottom - top)))
    xs = _edges(left, right - left, cols)
    ys = _edges(top, bottom - top, rows)
    return _make_cell(row, col, xs, ys)


def point_for_cell(label: str, rows: int, cols: int, *,
                   region: Optional[Sequence[int]] = None,
                   screen_size: Optional[Sequence[int]] = None) -> List[int]:
    """Return the centre point ``[x, y]`` of the cell named ``label`` (e.g. ``'C3'``)."""
    rows, cols = _validate(rows, cols)
    match = _LABEL_RE.fullmatch(label.strip())
    if not match:
        raise ValueError(f"invalid cell label: {label!r}")
    col, row = _col_index(match.group(1)), int(match.group(2)) - 1
    if not (0 <= col < cols and 0 <= row < rows):
        raise ValueError(f"cell {label!r} is outside a {rows}x{cols} grid")
    left, top, right, bottom = _bounds(region, screen_size)
    xs = _edges(left, right - left, cols)
    ys = _edges(top, bottom - top, rows)
    return _make_cell(row, col, xs, ys).center
