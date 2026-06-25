"""Associate form labels with their values and read checkbox state.

``ocr/structure`` recognises a label only if its text ends in ``:`` and pairs it with the
*immediately next* cell — it cannot handle a label sitting *above* its value, a two-column
key/value layout, right-aligned values, or any widget that isn't a text cell, and it has no
notion of checkbox / radio state at all. ``form_fields`` generalises this: it pairs each
label with the nearest aligned value in any of several *directions* (right, below), matches
free-standing widgets (checkboxes, radios, inputs) to their nearest label, and reads a
checkbox's checked state from its fill ratio.

The association is pure-stdlib over plain box dicts (fully unit-testable, no image); only
``checkbox_state`` touches pixels, isolated behind the shared ``visual_match`` gray loader so
tests can pass a synthetic array. Reuses ``table_grid_fill``'s box-bounds reader. Imports no
``PySide6``.
"""
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.table_grid_fill.table_grid_fill import _box_bounds

Box = Dict[str, Any]


def _overlap_1d(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _right_value(label: Box, values: Sequence[Box], max_gap: int):
    """Nearest value to the right of ``label`` that shares a row, or ``None``."""
    _, top, right, bottom = _box_bounds(label)
    best: Optional[Tuple[Box, int]] = None
    for value in values:
        vl, vt, _, vb = _box_bounds(value)
        gap = vl - right
        if vl >= right and _overlap_1d(top, bottom, vt, vb) > 0 and 0 <= gap <= max_gap \
                and (best is None or gap < best[1]):
            best = (value, gap)
    return best


def _below_value(label: Box, values: Sequence[Box], max_gap: int):
    """Nearest value below ``label`` that shares a column, or ``None``."""
    left, _, right, bottom = _box_bounds(label)
    best: Optional[Tuple[Box, int]] = None
    for value in values:
        vl, vt, vr, _ = _box_bounds(value)
        gap = vt - bottom
        if vt >= bottom and _overlap_1d(left, right, vl, vr) > 0 and 0 <= gap <= max_gap \
                and (best is None or gap < best[1]):
            best = (value, gap)
    return best


_DIRECTIONS: Dict[str, Callable[[Box, Sequence[Box], int], Any]] = {
    "right": _right_value, "below": _below_value}


def _clean_label(box: Box) -> str:
    return str(box.get("text", "")).strip().rstrip(":").strip()


def _best_value(label: Box, values: Sequence[Box], directions: Sequence[str],
                max_gap: int):
    """Pick the nearest value across the requested directions, or ``None``."""
    best = None
    for direction in directions:
        candidate = _DIRECTIONS[direction](label, values, max_gap)
        if candidate is not None and (best is None or candidate[1] < best[1]):
            best = (candidate[0], candidate[1], direction)
    return best


def associate_fields(text_boxes: Sequence[Box], *,
                     directions: Sequence[str] = ("right", "below"),
                     max_gap: int = 150) -> List[Dict[str, Any]]:
    """Pair each ``label:`` box with its nearest aligned value box.

    Labels are boxes whose text ends in ``:``; every other box is a candidate value.
    Returns ``{label, value, direction, gap, label_box, value_box}`` per matched label.
    """
    labels = [b for b in text_boxes if str(b.get("text", "")).strip().endswith(":")]
    label_ids = {id(b) for b in labels}
    values = [b for b in text_boxes if id(b) not in label_ids]
    fields: List[Dict[str, Any]] = []
    for label in labels:
        best = _best_value(label, values, directions, int(max_gap))
        if best is not None:
            fields.append({"label": _clean_label(label),
                           "value": str(best[0].get("text", "")),
                           "direction": best[2], "gap": best[1],
                           "label_box": label, "value_box": best[0]})
    return fields


def match_labels_to_widgets(labels: Sequence[Box],
                            widgets: Sequence[Box]) -> List[Dict[str, Any]]:
    """Match each widget (checkbox / radio / input) to its nearest label by centre."""
    pairs: List[Dict[str, Any]] = []
    for widget in widgets:
        wl, wt, wr, wb = _box_bounds(widget)
        wcx, wcy = (wl + wr) // 2, (wt + wb) // 2
        best: Optional[Tuple[Box, int]] = None
        for label in labels:
            ll, lt, lr, lb = _box_bounds(label)
            dist = abs(wcx - (ll + lr) // 2) + abs(wcy - (lt + lb) // 2)
            if best is None or dist < best[1]:
                best = (label, dist)
        if best is not None:
            pairs.append({"widget": widget, "label": str(best[0].get("text", "")),
                          "distance": best[1]})
    return pairs


def checkbox_state(image: Any, box: Box, *, fill_threshold: float = 0.15) -> str:
    """Return ``"checked"`` / ``"unchecked"`` from the dark-pixel fill ratio of ``box``."""
    import numpy as np
    from je_auto_control.utils.visual_match.visual_match import _to_gray
    left, top, right, bottom = _box_bounds(box)
    patch = _to_gray(image)[top:bottom, left:right]
    if patch.size == 0:
        return "unchecked"
    filled = float(np.count_nonzero(patch < 128)) / patch.size
    return "checked" if filled >= float(fill_threshold) else "unchecked"
