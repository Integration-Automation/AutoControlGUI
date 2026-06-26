"""Classify what kind of widget a box is from its pixel shape.

Set-of-Marks and element proposers hand back *boxes*, but not *what each box is*.
``form_fields.checkbox_state`` already reads a box known to be a checkbox; the
gap is the typing step before it — is this box a checkbox, a radio button, a
push button, a text field or a toggle? ``icon_classify`` answers that from cheap
geometric features (no model):

* :func:`box_features` — extract ``{aspect, fill, edge_density, circularity}``
  for a box region (the objective measurements).
* :func:`classify_widget` — pure: map a feature dict to a widget type by
  documented heuristics.
* :func:`classify_icon` — compose the two: a box to ``{type, features}``.

``classify_widget`` is pure and fully testable; ``box_features`` imports cv2 /
numpy lazily (the module stays importable without them) and reuses
:func:`visual_match._to_gray`. Imports no ``PySide6``.
"""
from typing import Any, Dict, Sequence

# The widget types this classifier can return.
WIDGET_TYPES = ("radio", "toggle", "checkbox", "text_field", "button", "icon")


def _is_round(aspect: float, circ: float) -> bool:
    """Near-square and circular (a radio button / round dot)."""
    return 0.7 <= aspect <= 1.4 and circ >= 0.7


def _is_pill(aspect: float, circ: float) -> bool:
    """Wide and rounded (a toggle switch)."""
    return 1.8 <= aspect <= 3.5 and circ >= 0.55


def classify_widget(features: Dict[str, float]) -> str:
    """Map geometric ``features`` to a widget type by heuristics (pure).

    Uses ``aspect`` (w/h), ``circularity`` (1 = circle), and ``fill`` (ink
    fraction). Round → ``radio``; wide & rounded → ``toggle``; near-square &
    sparse → ``checkbox``; wide & hollow → ``text_field``; wide & filled →
    ``button``; otherwise ``icon``.
    """
    aspect = float(features.get("aspect", 1.0))
    circ = float(features.get("circularity", 0.0))
    fill = float(features.get("fill", 0.0))
    if _is_round(aspect, circ):
        return "radio"
    if _is_pill(aspect, circ):
        return "toggle"
    if 0.7 <= aspect <= 1.4 and fill <= 0.6:
        return "checkbox"
    if aspect >= 2.5 and fill <= 0.2:
        return "text_field"
    if aspect >= 1.5 and fill >= 0.2:
        return "button"
    return "icon"


def _circularity(binary: Any) -> float:
    """Circularity (``4*pi*A / P^2``, 1 = circle) of the largest blob."""
    import math

    import cv2
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    largest = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(largest))
    perimeter = float(cv2.arcLength(largest, True))
    if perimeter <= 0.0:
        return 0.0
    return min(1.0, 4.0 * math.pi * area / (perimeter * perimeter))


def box_features(source: Any, box: Sequence[int]) -> Dict[str, float]:
    """Extract ``{aspect, fill, edge_density, circularity}`` for a box (cv2).

    ``aspect`` is width/height, ``fill`` the ink fraction (Otsu foreground),
    ``edge_density`` the Canny-edge fraction, ``circularity`` the largest blob's
    roundness. An empty box yields all zeros.
    """
    import cv2
    from je_auto_control.utils.visual_match.visual_match import _to_gray
    gray = _to_gray(source)
    x, y, w, h = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
    patch = gray[max(0, y):y + h, max(0, x):x + w]
    if patch.size == 0:
        return {"aspect": 0.0, "fill": 0.0, "edge_density": 0.0,
                "circularity": 0.0}
    _, binary = cv2.threshold(patch, 0, 255,
                              cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    fill = float((binary > 0).sum()) / patch.size
    edges = cv2.Canny(patch, 50, 150)
    edge_density = float((edges > 0).sum()) / patch.size
    return {
        "aspect": round(w / h, 3) if h else 0.0,
        "fill": round(fill, 3),
        "edge_density": round(edge_density, 3),
        "circularity": round(_circularity(binary), 3),
    }


def classify_icon(source: Any, box: Sequence[int]) -> Dict[str, Any]:
    """Classify the widget in a box from its pixels: ``{type, features}``."""
    features = box_features(source, box)
    return {"type": classify_widget(features), "features": features}
