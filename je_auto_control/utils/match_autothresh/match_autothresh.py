"""Auto-derive a template-match threshold from the score map (Otsu).

Every call to ``match_template_all`` forces the caller to guess ``min_score``: too low
floods NMS with background noise, too high drops scaled / re-themed targets, and the right
value differs per asset and per screen. ``match_autothresh`` removes the magic number — it
runs Otsu's method on the *correlation score histogram* (not pixel intensities, the way
``preprocess.binarize`` does) to find the valley between the "background correlation" mass
and the "real match" mass, and returns that cut-off plus a *separability* number so the
caller knows when the histogram is unimodal (no clear match → don't trust the threshold).

It reuses ``visual_match._score_map`` — the full ``matchTemplate`` surface the public
matchers discard — plus the shared ``Match`` / ``_nms``. The ``haystack`` is injectable
(ndarray / path / PIL); the analysis is unit-testable on synthetic arrays. OpenCV + NumPy
are imported lazily. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.visual_match.visual_match import Match, _score_map

ImageSource = Any


def _separability(scaled, threshold: float) -> float:
    """Otsu separability eta = between-class variance / total variance (0..1)."""
    total_var = float(scaled.var())
    if total_var < 1e-9:
        return 0.0
    below, above = scaled[scaled <= threshold], scaled[scaled > threshold]
    if below.size == 0 or above.size == 0:
        return 0.0
    weight0, weight1 = below.size / scaled.size, above.size / scaled.size
    between = weight0 * weight1 * (float(below.mean()) - float(above.mean())) ** 2
    return max(0.0, min(1.0, between / total_var))


def _otsu_on_scores(score_map):
    """Return ``(threshold_in_score_units, separability)`` for a correlation surface."""
    import cv2
    import numpy as np
    low, high = float(score_map.min()), float(score_map.max())
    if high - low < 1e-9:
        return low, 0.0
    scaled = ((score_map - low) / (high - low) * 255.0).astype(np.uint8)
    level, _ = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = low + (float(level) / 255.0) * (high - low)
    return threshold, _separability(scaled, float(level))


def auto_threshold(template: ImageSource, *, haystack: Optional[ImageSource] = None,
                   region: Optional[Sequence[int]] = None,
                   method: str = "ccoeff_normed") -> Optional[Dict[str, Any]]:
    """Return an Otsu-derived accept cut-off for ``template``, or ``None``.

    ``{threshold, separability, n_above}`` — ``separability`` near 0 means the score
    histogram is unimodal (no clear match) and the threshold should not be trusted.
    """
    import numpy as np
    score_map, _ = _score_map(template, haystack, region=region, method=method)
    if score_map is None:
        return None
    threshold, separability = _otsu_on_scores(score_map)
    return {"threshold": round(threshold, 4),
            "separability": round(separability, 4),
            "n_above": int(np.count_nonzero(score_map >= threshold))}


def _peak_in_box(score_map, box: Dict[str, Any]):
    """Return ``(x, y, score)`` of the highest score inside one connected blob box."""
    import numpy as np
    x, y, width, height = box["x"], box["y"], box["width"], box["height"]
    sub = score_map[y:y + height, x:x + width]
    iy, ix = np.unravel_index(int(np.argmax(sub)), sub.shape)
    return x + int(ix), y + int(iy), float(sub[iy, ix])


def match_auto(template: ImageSource, *, haystack: Optional[ImageSource] = None,
               region: Optional[Sequence[int]] = None, floor: float = 0.5,
               method: str = "ccoeff_normed", max_results: int = 20) -> List[Match]:
    """Return one match per above-threshold region (auto cut-off clamped by ``floor``).

    The cut-off is ``max(floor, otsu_threshold)`` so a unimodal / noisy surface cannot
    drag the threshold below a sane floor. Each connected above-threshold region yields
    a single peak (its highest score), avoiding the duplicate hits a raw pixel scan +
    NMS leaves on a wide correlation peak. Ordered by score, capped at ``max_results``.
    """
    import numpy as np
    from je_auto_control.utils.cv2_utils.blobs import connected_boxes
    score_map, tmpl = _score_map(template, haystack, region=region, method=method)
    if score_map is None:
        return []
    threshold, _ = _otsu_on_scores(score_map)
    cutoff = max(float(floor), threshold)
    mask = (score_map >= cutoff).astype(np.uint8)
    height, width = tmpl.shape[:2]
    matches = [Match(px, py, width, height, round(score, 4), 1.0)
               for px, py, score in
               (_peak_in_box(score_map, box) for box in connected_boxes(mask))]
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:int(max_results)]
