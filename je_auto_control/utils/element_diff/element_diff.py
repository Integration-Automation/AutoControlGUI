"""Geometry-aware element matching across frames — stable IDs, move tracking.

``screen_state.diff_snapshots`` keys element identity strictly on ``(role, name)`` — so
it cannot match an element whose label changed but position is stable, cannot track a
renamed control, and cannot produce persistent IDs across frames. Geometry-aware
matching (intersection-over-union, reusing :doc:`v138_features_doc`'s ``iou``) is the
basis for stable element IDs an agent can refer to turn-over-turn: a button that moved
3px keeps its id, a renamed-but-stationary control matches by overlap, a genuinely new
element gets a fresh id.

Pure-stdlib over plain element dicts (``x`` / ``y`` / ``width`` / ``height``), so it is
fully unit-testable. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.element_parse import iou

Element = Dict[str, Any]


def match_elements(before: Sequence[Element], after: Sequence[Element], *,
                   iou_threshold: float = 0.5) -> Dict[str, Any]:
    """Greedily match ``before`` elements to ``after`` by overlap.

    Returns ``{matched: [{before, after, iou}], added: [...], removed: [...]}`` — a
    ``before`` element with no overlap above ``iou_threshold`` is *removed*, an
    unmatched ``after`` element is *added*.
    """
    after = list(after)
    taken: set = set()
    matched: List[Dict[str, Any]] = []
    removed: List[Element] = []
    for element in before:
        best_index, best_score = -1, float(iou_threshold)
        for index, candidate in enumerate(after):
            if index in taken:
                continue
            score = iou(element, candidate)
            if score >= best_score:
                best_index, best_score = index, score
        if best_index >= 0:
            taken.add(best_index)
            matched.append({"before": element, "after": after[best_index],
                            "iou": round(best_score, 4)})
        else:
            removed.append(element)
    added = [candidate for index, candidate in enumerate(after)
             if index not in taken]
    return {"matched": matched, "added": added, "removed": removed}


def _best_prior(element: Element, prior: Sequence[Element],
                iou_threshold: float) -> Optional[Element]:
    best, best_score = None, float(iou_threshold)
    for candidate in prior:
        score = iou(element, candidate)
        if score >= best_score:
            best, best_score = candidate, score
    return best


def assign_stable_ids(elements: Sequence[Element],
                      prior: Optional[Sequence[Element]] = None, *,
                      iou_threshold: float = 0.5) -> List[Element]:
    """Return ``elements`` each tagged with a stable ``id``, carried from ``prior``.

    With no ``prior`` every element gets a fresh sequential id; otherwise each element
    inherits the id of the ``prior`` element it most overlaps (above ``iou_threshold``),
    and unmatched elements get new ids beyond the highest prior id.
    """
    if not prior:
        return [dict(element, id=index) for index, element in enumerate(elements)]
    next_id = max((int(p.get("id", -1)) for p in prior), default=-1) + 1
    result: List[Element] = []
    for element in elements:
        match = _best_prior(element, prior, float(iou_threshold))
        if match is not None and "id" in match:
            result.append(dict(element, id=int(match["id"])))
        else:
            result.append(dict(element, id=next_id))
            next_id += 1
    return result
