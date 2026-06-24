"""Detect the display scale a template renders at (visual DPI).

A template cropped at 100% display scale will not match pixel-for-pixel on a
machine running at 150% DPI — everything is 1.5x bigger. ``visual_match.
match_template`` *can* sweep scales, but it returns only the single best match's
location and throws the per-scale scores away. ``scale_detect`` keeps the whole
profile: it scores the template against the haystack at a range of scales and
reports *which scale wins, by how much*, so an automation can infer the effective
UI scale / DPI and how confident that inference is.

It reuses ``visual_match._score_map`` (the full ``matchTemplate`` surface,
oriented higher = better) for each scale, so the source is any ndarray / path /
PIL image (or the live screen). cv2 / numpy are lazily imported. Imports no
``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

ImageSource = Any
# Common Windows display scales (100% / 125% / 150% / 175% / 200%).
_DEFAULT_SCALES = (1.0, 1.25, 1.5, 1.75, 2.0)


def _score_at(template: ImageSource, haystack: Optional[ImageSource],
              region: Optional[Sequence[int]], method: str,
              scale: float) -> Optional[Dict[str, Any]]:
    import cv2
    from je_auto_control.utils.visual_match.visual_match import _score_map
    score_map, tmpl = _score_map(template, haystack, region=region,
                                 method=method, scale=scale)
    if score_map is None:
        return None  # template larger than haystack at this scale
    _min_v, max_v, _min_loc, max_loc = cv2.minMaxLoc(score_map)
    height, width = int(tmpl.shape[0]), int(tmpl.shape[1])
    x, y = int(max_loc[0]), int(max_loc[1])
    return {"scale": float(scale), "score": float(max_v), "x": x, "y": y,
            "width": width, "height": height,
            "center": [x + width // 2, y + height // 2]}


def scale_sweep(template: ImageSource, haystack: Optional[ImageSource] = None, *,
                region: Optional[Sequence[int]] = None,
                scales: Optional[Sequence[float]] = None,
                method: str = "ccoeff_normed") -> List[Dict[str, Any]]:
    """Score ``template`` against the haystack at each scale.

    Returns ``[{scale, score, x, y, width, height, center}]`` (best match per
    scale), skipping scales at which the template is larger than the haystack.
    """
    chosen = tuple(scales) if scales else _DEFAULT_SCALES
    results = []
    for scale in chosen:
        entry = _score_at(template, haystack, region, method, float(scale))
        if entry is not None:
            results.append(entry)
    return results


def detect_scale(template: ImageSource, haystack: Optional[ImageSource] = None, *,
                 region: Optional[Sequence[int]] = None,
                 scales: Optional[Sequence[float]] = None,
                 method: str = "ccoeff_normed") -> Optional[Dict[str, Any]]:
    """Infer the display scale ``template`` renders at (its visual DPI).

    Returns ``{scale, scale_percent, score, center, margin, candidates}`` — the
    winning scale, its percentage, the match score, and ``margin`` (how far it
    beats the runner-up: a confidence in the inference). ``None`` if no scale
    matched (template never fit the haystack).
    """
    sweep = scale_sweep(template, haystack, region=region, scales=scales,
                        method=method)
    if not sweep:
        return None
    ranked = sorted(sweep, key=lambda entry: entry["score"], reverse=True)
    best = ranked[0]
    margin = best["score"] - ranked[1]["score"] if len(ranked) > 1 else best["score"]
    return {"scale": best["scale"], "scale_percent": round(best["scale"] * 100),
            "score": best["score"], "center": best["center"],
            "margin": float(margin), "candidates": sweep}
