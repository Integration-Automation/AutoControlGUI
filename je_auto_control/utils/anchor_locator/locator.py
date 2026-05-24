"""Anchor-based locator: find element B by spatial relation to anchor A.

Composes the existing image / OCR / VLM / accessibility backends so
the anchor and the target can each use a different strategy. The
canonical use case is *"the green Submit button below the Username
field"* — Username is the anchor (located by OCR), Submit is the
target (located by template match), and the spatial relation
``"below"`` removes false positives that would otherwise sit at the
top of the form.

Headless and Qt-free. Returns a :class:`AnchorOutcome` dict-able
result that the executor / MCP layer can serialise straight to JSON.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


# Spatial relations the wrapper understands.
REL_ABOVE = "above"
REL_BELOW = "below"
REL_LEFT_OF = "left_of"
REL_RIGHT_OF = "right_of"
REL_NEAR = "near"
_VALID_RELATIONS = frozenset({
    REL_ABOVE, REL_BELOW, REL_LEFT_OF, REL_RIGHT_OF, REL_NEAR,
})

# Locator backend kinds.
KIND_IMAGE = "image"
KIND_OCR = "ocr"
KIND_VLM = "vlm"
KIND_A11Y = "a11y"
_VALID_KINDS = frozenset({KIND_IMAGE, KIND_OCR, KIND_VLM, KIND_A11Y})


class AnchorLocatorError(ValueError):
    """Raised when a locator spec is invalid or an anchor cannot be resolved."""


@dataclass(frozen=True)
class Locator:
    """Description of how to find one element on screen.

    Only the fields relevant to ``kind`` are read; the rest stay None.
    Build via :func:`image_locator`, :func:`ocr_locator`,
    :func:`vlm_locator`, :func:`a11y_locator` for clarity.
    """

    kind: str
    template_path: Optional[str] = None
    detect_threshold: float = 0.9
    text: Optional[str] = None
    min_confidence: float = 60.0
    region: Optional[Tuple[int, int, int, int]] = None
    description: Optional[str] = None
    model: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    app_name: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise AnchorLocatorError(
                f"kind must be one of {sorted(_VALID_KINDS)}, got {self.kind!r}",
            )


def image_locator(template_path: str,
                  detect_threshold: float = 0.9) -> Locator:
    return Locator(kind=KIND_IMAGE,
                    template_path=str(template_path),
                    detect_threshold=float(detect_threshold))


def ocr_locator(text: str, *, min_confidence: float = 60.0,
                region: Optional[List[int]] = None) -> Locator:
    return Locator(
        kind=KIND_OCR, text=str(text),
        min_confidence=float(min_confidence),
        region=tuple(region) if region else None,
    )


def vlm_locator(description: str,
                model: Optional[str] = None) -> Locator:
    return Locator(kind=KIND_VLM, description=str(description),
                    model=model)


def a11y_locator(*, role: Optional[str] = None,
                  name: Optional[str] = None,
                  app_name: Optional[str] = None) -> Locator:
    if not any([role, name, app_name]):
        raise AnchorLocatorError("a11y_locator needs at least one of role / name / app_name")
    return Locator(kind=KIND_A11Y, role=role, name=name, app_name=app_name)


@dataclass(frozen=True)
class _Bbox:
    """Internal axis-aligned bounding box."""

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2


@dataclass(frozen=True)
class AnchorOutcome:
    """Result of one anchor-based locate."""

    found: bool
    target_coords: Optional[Tuple[int, int]]
    anchor_coords: Optional[Tuple[int, int]]
    distance_px: Optional[float]
    relation: str
    target_kind: str
    anchor_kind: str
    candidates_considered: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.target_coords is not None:
            data["target_coords"] = list(self.target_coords)
        if self.anchor_coords is not None:
            data["anchor_coords"] = list(self.anchor_coords)
        return data


def anchor_locate(*, anchor: Locator, target: Locator,
                   relation: str = REL_NEAR,
                   max_distance_px: float = 200.0) -> AnchorOutcome:
    """Find ``target`` near / above / below / beside ``anchor``.

    Strategy:

    1. Resolve the anchor to one (x, y) point. VLM / a11y / image
       template / OCR all collapse to a centre.
    2. Resolve the target to a list of candidate bboxes. Image and
       OCR can enumerate; VLM / a11y always return one point so
       only that one candidate is considered.
    3. Filter candidates by the spatial relation; tie-break by the
       smallest centre-to-centre distance.
    """
    relation_norm = _normalise_relation(relation)
    anchor_point = _resolve_single(anchor)
    if anchor_point is None:
        return AnchorOutcome(
            found=False, target_coords=None, anchor_coords=None,
            distance_px=None, relation=relation_norm,
            target_kind=target.kind, anchor_kind=anchor.kind,
            error="anchor not found",
        )
    candidates = _resolve_candidates(target)
    candidates_considered = len(candidates)
    if not candidates:
        return AnchorOutcome(
            found=False, target_coords=None, anchor_coords=anchor_point,
            distance_px=None, relation=relation_norm,
            target_kind=target.kind, anchor_kind=anchor.kind,
            candidates_considered=0, error="target not found",
        )
    chosen = _pick_best(
        anchor_point, candidates, relation_norm, float(max_distance_px),
    )
    if chosen is None:
        return AnchorOutcome(
            found=False, target_coords=None, anchor_coords=anchor_point,
            distance_px=None, relation=relation_norm,
            target_kind=target.kind, anchor_kind=anchor.kind,
            candidates_considered=candidates_considered,
            error=f"no candidate satisfies relation {relation_norm!r}",
        )
    coords, distance = chosen
    return AnchorOutcome(
        found=True, target_coords=coords, anchor_coords=anchor_point,
        distance_px=round(distance, 2), relation=relation_norm,
        target_kind=target.kind, anchor_kind=anchor.kind,
        candidates_considered=candidates_considered,
    )


def _normalise_relation(relation: str) -> str:
    normalised = (relation or "").strip().lower()
    if normalised not in _VALID_RELATIONS:
        raise AnchorLocatorError(
            f"relation must be one of {sorted(_VALID_RELATIONS)}, "
            f"got {relation!r}",
        )
    return normalised


def _resolve_single(locator: Locator) -> Optional[Tuple[int, int]]:
    if locator.kind == KIND_IMAGE:
        return _image_center(locator)
    if locator.kind == KIND_OCR:
        return _ocr_center(locator)
    if locator.kind == KIND_VLM:
        return _vlm_point(locator)
    if locator.kind == KIND_A11Y:
        return _a11y_point(locator)
    return None


def _resolve_candidates(locator: Locator) -> List[_Bbox]:
    if locator.kind == KIND_IMAGE:
        return _image_candidates(locator)
    if locator.kind == KIND_OCR:
        return _ocr_candidates(locator)
    if locator.kind in (KIND_VLM, KIND_A11Y):
        point = _resolve_single(locator)
        return [] if point is None else [_point_as_bbox(point)]
    return []


def _pick_best(anchor_point: Tuple[int, int],
                candidates: List[_Bbox],
                relation: str,
                max_distance: float,
                ) -> Optional[Tuple[Tuple[int, int], float]]:
    best: Optional[Tuple[Tuple[int, int], float]] = None
    for bbox in candidates:
        if not _matches_relation(anchor_point, bbox, relation):
            continue
        distance = _euclid(anchor_point, bbox.center)
        if relation == REL_NEAR and distance > max_distance:
            continue
        if best is None or distance < best[1]:
            best = (bbox.center, distance)
    return best


def _matches_relation(anchor_point: Tuple[int, int],
                       bbox: _Bbox, relation: str) -> bool:
    ax, ay = anchor_point
    cx, cy = bbox.center
    if relation == REL_NEAR:
        return True
    if relation == REL_ABOVE:
        return cy < ay
    if relation == REL_BELOW:
        return cy > ay
    if relation == REL_LEFT_OF:
        return cx < ax
    if relation == REL_RIGHT_OF:
        return cx > ax
    return False


def _euclid(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _point_as_bbox(point: Tuple[int, int]) -> _Bbox:
    return _Bbox(x1=point[0], y1=point[1], x2=point[0], y2=point[1])


# --- backend adapters -------------------------------------------

def _image_center(locator: Locator) -> Optional[Tuple[int, int]]:
    try:
        from je_auto_control.wrapper.auto_control_image import (
            locate_image_center,
        )
        return locate_image_center(
            locator.template_path,
            detect_threshold=locator.detect_threshold,
        )
    except (OSError, RuntimeError, ValueError):
        return None


def _image_candidates(locator: Locator) -> List[_Bbox]:
    try:
        from je_auto_control.wrapper.auto_control_image import (
            locate_all_image,
        )
        rows = locate_all_image(
            locator.template_path,
            detect_threshold=locator.detect_threshold,
        )
    except (OSError, RuntimeError, ValueError):
        return []
    return [_Bbox(*map(int, row[:4])) for row in rows
            if isinstance(row, (list, tuple)) and len(row) >= 4]


def _ocr_center(locator: Locator) -> Optional[Tuple[int, int]]:
    try:
        from je_auto_control.utils.ocr.ocr_engine import locate_text_center
        return locate_text_center(
            locator.text,
            region=list(locator.region) if locator.region else None,
            min_confidence=locator.min_confidence,
        )
    except (OSError, RuntimeError, ValueError):
        return None


def _ocr_candidates(locator: Locator) -> List[_Bbox]:
    try:
        from je_auto_control.utils.ocr.ocr_engine import find_text_matches
        matches = find_text_matches(
            locator.text,
            region=list(locator.region) if locator.region else None,
            min_confidence=locator.min_confidence,
        )
    except (OSError, RuntimeError, ValueError):
        return []
    return [_Bbox(x1=m.x, y1=m.y, x2=m.x + m.width, y2=m.y + m.height)
            for m in matches]


def _vlm_point(locator: Locator) -> Optional[Tuple[int, int]]:
    try:
        from je_auto_control.utils.vision.vlm_api import locate_by_description
        return locate_by_description(
            locator.description, model=locator.model,
        )
    except (OSError, RuntimeError, ValueError):
        return None


def _a11y_point(locator: Locator) -> Optional[Tuple[int, int]]:
    try:
        from je_auto_control.utils.accessibility.accessibility_api import (
            find_accessibility_element,
        )
        element = find_accessibility_element(
            name=locator.name, role=locator.role, app_name=locator.app_name,
        )
    except (OSError, RuntimeError, ValueError):
        return None
    if element is None:
        return None
    bounds = getattr(element, "bounds", None)
    if not (isinstance(bounds, (list, tuple)) and len(bounds) >= 4):
        return None
    x, y, w, h = (int(v) for v in bounds[:4])
    return x + w // 2, y + h // 2


__all__ = [
    "AnchorLocatorError", "AnchorOutcome", "KIND_A11Y", "KIND_IMAGE",
    "KIND_OCR", "KIND_VLM", "Locator", "REL_ABOVE", "REL_BELOW",
    "REL_LEFT_OF", "REL_NEAR", "REL_RIGHT_OF", "a11y_locator",
    "anchor_locate", "image_locator", "ocr_locator", "vlm_locator",
]
