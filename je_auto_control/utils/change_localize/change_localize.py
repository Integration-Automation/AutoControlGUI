"""Attribute a screen change to the specific elements that changed.

The existing diffs answer "*where* did pixels change" (``motion_regions``,
``perceptual_diff``, ``ssim_changed_regions`` return raw pixel regions) or "which
*accessibility* elements differ" (``element_diff``, needs a11y metadata). The
missing middle is: given a frame diff **and a list of element boxes**, which of
*those* elements changed? ``change_localize`` scores each supplied box by how
much it changed and ranks them.

* :func:`rank_changes` — pure: take ``[{box, score}]`` and mark each box
  ``changed`` (score at or above ``threshold``), sorted most-changed first.
* :func:`localize_changes` — diff a reference against the current screen, score
  each element box by its mean pixel change, and rank them.

cv2 / numpy are imported lazily (the module stays importable without them) and
the loaders reuse :mod:`visual_match`. The ranking is pure and fully testable.
Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence


def _unpack(item: Any) -> tuple:
    """Return ``(box, score)`` from a ``{box, score}`` dict or a ``(box, score)``."""
    if isinstance(item, dict):
        return item["box"], item["score"]
    return item[0], item[1]


def rank_changes(scored_boxes: Sequence[Any], *,
                 threshold: float = 0.1) -> List[Dict[str, Any]]:
    """Mark and rank scored element boxes by how much they changed (pure).

    ``scored_boxes`` is a sequence of ``{box, score}`` (or ``(box, score)``).
    Returns ``[{box, score, changed}]`` sorted by descending score; ``changed``
    is ``True`` when the score is at or above ``threshold``.
    """
    limit = float(threshold)
    result = [
        {"box": [int(value) for value in box],
         "score": round(float(score), 4),
         "changed": float(score) >= limit}
        for box, score in (_unpack(item) for item in scored_boxes)
    ]
    result.sort(key=lambda entry: entry["score"], reverse=True)
    return result


def _box_mean(diff: Any, box: Sequence[int]) -> float:
    """Mean change (0..1) of the diff map inside ``box`` (numpy)."""
    x, y, w, h = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
    patch = diff[max(0, y):y + h, max(0, x):x + w]
    return float(patch.mean()) if patch.size else 0.0


def localize_changes(reference: Any, boxes: Sequence[Sequence[int]], *,
                     current: Optional[Any] = None, threshold: float = 0.1,
                     region: Optional[Sequence[int]] = None
                     ) -> List[Dict[str, Any]]:
    """Score and rank which of ``boxes`` changed between two frames.

    Diffs ``reference`` against ``current`` (a fresh screen grab of ``region``
    by default), takes each box's mean per-pixel change (0..1), and ranks them
    via :func:`rank_changes`. Returns ``[{box, score, changed}]``.
    """
    import numpy as np
    from je_auto_control.utils.visual_match.visual_match import (
        _grab_gray, _to_gray)
    ref = _to_gray(reference).astype("float64")
    other = current if current is not None else _grab_gray(region)
    cur = _to_gray(other).astype("float64")
    diff = np.abs(ref - cur) / 255.0
    scored = [{"box": list(box), "score": _box_mean(diff, box)}
              for box in boxes]
    return rank_changes(scored, threshold=threshold)
