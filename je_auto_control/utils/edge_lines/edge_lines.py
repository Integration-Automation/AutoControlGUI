"""Line, grid and separator detection on raw pixels (Hough) — tables and dividers.

``grid_locator`` clusters *already-found* element boxes into a grid; it cannot find
the ruling lines of a table / spreadsheet or a UI divider from raw pixels, and
``shape_locator`` only finds closed rectangles. This detects straight line segments
via Canny + the probabilistic Hough transform, classifies them horizontal / vertical /
diagonal, recovers a table's row/column coordinates and cells, and returns the
positions of long divider lines — so a script can address "row 3, column 2" or split a
panel at its separators without templates.

Runs on an injectable ``haystack`` (ndarray / path / PIL), so it is headless-testable
on synthetic arrays. ``cv2.HoughLinesP`` is base OpenCV; OpenCV + NumPy come in via
``je_open_cv``. Imports no ``PySide6``.
"""
import math
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.visual_match.visual_match import _haystack_gray

ImageSource = Any
_CANNY_LOW = 50
_CANNY_HIGH = 150


def _orientation(angle: float) -> str:
    a = abs(angle) % 180
    if a < 10 or a > 170:
        return "horizontal"
    if 80 < a < 100:
        return "vertical"
    return "diagonal"


def _segments(gray, min_length: int, max_gap: int):
    import cv2
    import numpy as np
    edges = cv2.Canny(gray, _CANNY_LOW, _CANNY_HIGH)
    return cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=50,
                           minLineLength=int(min_length), maxLineGap=int(max_gap))


def find_lines(haystack: Optional[ImageSource] = None, *,
               region: Optional[Sequence[int]] = None, min_length: int = 80,
               max_gap: int = 10, orientation: str = "any"
               ) -> List[Dict[str, Any]]:
    """Return straight line segments on screen, longest first.

    Each is ``{x1, y1, x2, y2, angle, length, orientation}`` where ``orientation`` is
    ``horizontal`` / ``vertical`` / ``diagonal``. Pass ``orientation`` other than
    ``any`` to keep only that kind. ``min_length`` / ``max_gap`` tune the Hough probe.
    """
    segments = _segments(_haystack_gray(haystack, region), int(min_length),
                         int(max_gap))
    out: List[Dict[str, Any]] = []
    if segments is None:
        return out
    for x1, y1, x2, y2 in segments[:, 0]:
        angle = math.degrees(math.atan2(int(y2) - int(y1), int(x2) - int(x1)))
        kind = _orientation(angle)
        if orientation not in ("any", kind):
            continue
        out.append({"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2),
                    "angle": round(angle, 1),
                    "length": round(math.hypot(x2 - x1, y2 - y1), 1),
                    "orientation": kind})
    out.sort(key=lambda seg: seg["length"], reverse=True)
    return out


def _cluster(values: Sequence[int], tol: int) -> List[int]:
    """Group near-equal coordinates and return each cluster's mean (sorted)."""
    groups: List[List[int]] = []
    for value in sorted(values):
        if groups and value - groups[-1][-1] <= tol:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [int(round(sum(group) / len(group))) for group in groups]


def find_separators(haystack: Optional[ImageSource] = None, *,
                    region: Optional[Sequence[int]] = None,
                    axis: str = "horizontal", min_length: int = 120,
                    tol: int = 10) -> List[int]:
    """Return the coordinates of long divider lines along ``axis``.

    ``axis="horizontal"`` returns the ``y`` of each horizontal rule (top-to-bottom);
    ``axis="vertical"`` returns the ``x`` of each vertical rule. Near-equal lines are
    merged within ``tol`` pixels.
    """
    lines = find_lines(haystack, region=region, min_length=int(min_length),
                       orientation=axis)
    coords = [seg["y1"] if axis == "horizontal" else seg["x1"] for seg in lines]
    return _cluster(coords, int(tol))


def find_grid(haystack: Optional[ImageSource] = None, *,
              region: Optional[Sequence[int]] = None, min_length: int = 120,
              tol: int = 10) -> Dict[str, Any]:
    """Recover a table's grid: ``{rows: [y…], cols: [x…], cells: [{x,y,width,height}]}``.

    Horizontal rules give the row coordinates, vertical rules the columns; the cells
    are the rectangles between consecutive rules. ``min_length`` filters short edges.
    """
    lines = find_lines(haystack, region=region, min_length=int(min_length))
    rows = _cluster([seg["y1"] for seg in lines
                     if seg["orientation"] == "horizontal"], int(tol))
    cols = _cluster([seg["x1"] for seg in lines
                     if seg["orientation"] == "vertical"], int(tol))
    cells = [{"x": cols[i], "y": rows[j], "width": cols[i + 1] - cols[i],
              "height": rows[j + 1] - rows[j]}
             for j in range(len(rows) - 1) for i in range(len(cols) - 1)]
    return {"rows": rows, "cols": cols, "cells": cells}
