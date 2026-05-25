"""Individual redaction detectors.

Each detector takes a PIL ``Image`` plus an optional context bag and
returns a list of bounding boxes ``(x1, y1, x2, y2)`` that should be
blurred. The engine merges the boxes and applies a single blur pass
so overlapping rectangles don't compound noise.

The OCR detectors are lazy: they import ``pytesseract`` (or the
``cv2_utils.ocr`` wrapper) only when the policy actually enables a
text-based rule, so a host that disables PII detection never pays the
OCR import cost.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from je_auto_control.utils.redaction.policies import (
    DETECTOR_CREDIT_CARD, DETECTOR_EMAIL, DETECTOR_PASSWORD_FIELD,
    DETECTOR_PHONE, DETECTOR_SSN,
)


BoundingBox = Tuple[int, int, int, int]
DetectorFn = Callable[[Any, Dict[str, Any]], List[BoundingBox]]


# --- Regex catalogue --------------------------------------------------------
# Bounded quantifiers keep every pattern provably linear-time so Sonar's
# S5852 doesn't trip on them.
_RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,24}\b",
)
_RE_CREDIT_CARD = re.compile(
    r"\b(?:\d{4}[ \-]?){3}\d{4}\b",
)
_RE_SSN = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b",
)
_RE_PHONE = re.compile(
    r"\b(?:\+?\d{1,3}[ .\-]?)?"
    r"\(?\d{3}\)?[ .\-]?\d{3}[ .\-]?\d{4}\b",
)


_REGEX_BY_DETECTOR: Dict[str, re.Pattern] = {
    DETECTOR_EMAIL: _RE_EMAIL,
    DETECTOR_CREDIT_CARD: _RE_CREDIT_CARD,
    DETECTOR_SSN: _RE_SSN,
    DETECTOR_PHONE: _RE_PHONE,
}


def regex_detector(name: str) -> DetectorFn:
    """Return a detector that blurs OCR-matched substrings for ``name``.

    The OCR step is supplied by the engine through ``context["ocr"]``
    — a list of ``(text, bbox)`` tuples. Detectors do not call OCR
    themselves so callers without OCR installed still get the
    region-based and accessibility rules.
    """
    pattern = _REGEX_BY_DETECTOR[name]

    def _detect(_image: Any, context: Dict[str, Any]) -> List[BoundingBox]:
        boxes: List[BoundingBox] = []
        for text, bbox in context.get("ocr", []) or []:
            if pattern.search(text or ""):
                boxes.append(_normalise_bbox(bbox))
        return boxes

    return _detect


def password_field_detector() -> DetectorFn:
    """Detector that blurs accessibility-flagged password input fields.

    Requires ``context["accessibility"]`` — a list of dicts with at
    least ``{"is_password": bool, "bbox": [x1, y1, x2, y2]}``. Hosts
    that haven't dumped the AX tree simply get an empty result.
    """
    def _detect(_image: Any, context: Dict[str, Any]) -> List[BoundingBox]:
        boxes: List[BoundingBox] = []
        for node in context.get("accessibility", []) or []:
            if not node.get("is_password"):
                continue
            bbox = node.get("bbox")
            if bbox is None:
                continue
            boxes.append(_normalise_bbox(bbox))
        return boxes

    return _detect


def static_region_detector(
        regions: Iterable[BoundingBox]) -> DetectorFn:
    """Detector that returns a fixed set of rectangles regardless of input."""
    boxed = [_normalise_bbox(r) for r in regions]

    def _detect(_image: Any, _context: Dict[str, Any]) -> List[BoundingBox]:
        return list(boxed)

    return _detect


def build_detector_chain(detectors: Iterable[str],
                         regions: Iterable[BoundingBox]) -> List[DetectorFn]:
    """Materialise a policy into the concrete detector callables."""
    chain: List[DetectorFn] = []
    for name in detectors:
        if name in _REGEX_BY_DETECTOR:
            chain.append(regex_detector(name))
        elif name == DETECTOR_PASSWORD_FIELD:
            chain.append(password_field_detector())
        # Unknown detector names are silently skipped — old policies
        # serialised to disk must keep loading after a rule rename.
    chain.append(static_region_detector(regions))
    return chain


def merge_boxes(boxes: Iterable[BoundingBox]) -> List[BoundingBox]:
    """Merge overlapping boxes so the blur step does one pass per region."""
    sorted_boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    merged: List[BoundingBox] = []
    for box in sorted_boxes:
        if not merged:
            merged.append(box)
            continue
        last = merged[-1]
        if _overlap(last, box):
            merged[-1] = (
                min(last[0], box[0]),
                min(last[1], box[1]),
                max(last[2], box[2]),
                max(last[3], box[3]),
            )
        else:
            merged.append(box)
    return merged


def _overlap(a: BoundingBox, b: BoundingBox) -> bool:
    return not (a[2] < b[0] or b[2] < a[0]
                or a[3] < b[1] or b[3] < a[1])


def _normalise_bbox(bbox) -> BoundingBox:
    if bbox is None:
        raise ValueError("bbox cannot be None")
    if isinstance(bbox, dict):
        x1 = int(bbox.get("x1", bbox.get("left", 0)))
        y1 = int(bbox.get("y1", bbox.get("top", 0)))
        x2 = int(bbox.get("x2", bbox.get("right", x1)))
        y2 = int(bbox.get("y2", bbox.get("bottom", y1)))
    else:
        seq = list(bbox)
        if len(seq) != 4:
            raise ValueError(f"bbox must have 4 values, got {len(seq)}")
        x1, y1, x2, y2 = (int(v) for v in seq)
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return (x1, y1, x2, y2)


__all__ = [
    "BoundingBox", "DetectorFn",
    "build_detector_chain", "merge_boxes",
    "password_field_detector", "regex_detector", "static_region_detector",
]
