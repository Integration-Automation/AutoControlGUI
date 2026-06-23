"""Trustworthiness scoring for template matches (second-peak ratio + PSR).

``visual_match.match_template`` returns the single best score and happily clicks it —
but a control repeated in a toolbar, or a near-identical sibling, correlates ~0.95 in
*two* places, so a high score does not mean an *unambiguous* match. This adds a Lowe-style
ratio test *for pixel templates* (``feature_match`` already does it for ORB keypoints, but
nothing did it for ``match_template``): it inspects the whole correlation surface, compares
the global peak against the next-best peak outside an exclusion window, and computes the
peak-to-sidelobe ratio (PSR), flagging matches that are strong-but-ambiguous.

It reuses ``visual_match._score_map`` (the full ``matchTemplate`` surface the public matchers
discard) plus the shared gray loaders, so no matching code is duplicated. The ``haystack`` is
injectable (ndarray / path / PIL); the search is unit-testable on synthetic arrays. OpenCV +
NumPy are imported lazily. Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.visual_match.visual_match import _score_map

ImageSource = Any


@dataclass(frozen=True)
class TrustedMatch:
    """A match plus its trust metrics: second-best score, peak ratio, PSR, ambiguity."""

    x: int
    y: int
    width: int
    height: int
    score: float
    scale: float
    second_score: float
    peak_ratio: float
    psr: Optional[float]
    is_ambiguous: bool

    @property
    def center(self) -> List[int]:
        """The match's centre point ``[x, y]`` (ready to click)."""
        return [self.x + self.width // 2, self.y + self.height // 2]

    def to_dict(self) -> Dict[str, Any]:
        """Return the match as a plain dict including the centre point."""
        data = asdict(self)
        data["center"] = self.center
        return data


def _safe_psr(value: float) -> Optional[float]:
    """Round the PSR, or ``None`` when the sidelobe has no variance (a perfect peak)."""
    import math
    return round(value, 4) if math.isfinite(value) else None


def _peak_stats(score_map, exclude_radius: int):
    """Return ``(loc, best, second, peak_ratio, psr)`` for one correlation surface."""
    import numpy as np
    height, width = score_map.shape
    best_y, best_x = divmod(int(np.argmax(score_map)), width)
    best = float(score_map[best_y, best_x])
    mask = np.ones(score_map.shape, dtype=bool)
    y0, y1 = max(0, best_y - exclude_radius), min(height, best_y + exclude_radius + 1)
    x0, x1 = max(0, best_x - exclude_radius), min(width, best_x + exclude_radius + 1)
    mask[y0:y1, x0:x1] = False
    sidelobe = score_map[mask]
    if sidelobe.size:
        second, mean, std = (float(sidelobe.max()), float(sidelobe.mean()),
                             float(sidelobe.std()))
    else:
        second, mean, std = 0.0, 0.0, 0.0
    peak_ratio = second / best if abs(best) > 1e-9 else 1.0
    psr = (best - mean) / std if std > 1e-9 else float("inf")
    return (best_x, best_y), best, second, peak_ratio, psr


def _default_radius(template_shape, exclude_radius: Optional[int]) -> int:
    """Pick the peak-exclusion radius: caller value, or a quarter of the smaller side."""
    if exclude_radius:
        return int(exclude_radius)
    return max(3, min(template_shape[:2]) // 4)


def score_peaks(template: ImageSource, *, haystack: Optional[ImageSource] = None,
                region: Optional[Sequence[int]] = None,
                exclude_radius: Optional[int] = None, method: str = "ccoeff_normed",
                ambiguous_ratio: float = 0.9) -> Optional[Dict[str, Any]]:
    """Return peak/sidelobe trust metrics for ``template`` at scale 1.0, or ``None``.

    ``{best, second, peak_ratio, psr, ambiguous, location}`` — ``peak_ratio`` near 1
    means a second place scored almost as high (ambiguous); ``psr`` is the
    peak-to-sidelobe ratio (``None`` when the sidelobe is flat).
    """
    score_map, tmpl = _score_map(template, haystack, region=region, method=method)
    if score_map is None:
        return None
    radius = _default_radius(tmpl.shape, exclude_radius)
    (peak_x, peak_y), best, second, ratio, psr = _peak_stats(score_map, radius)
    return {"best": round(best, 4), "second": round(second, 4),
            "peak_ratio": round(ratio, 4), "psr": _safe_psr(psr),
            "ambiguous": ratio >= ambiguous_ratio, "location": [peak_x, peak_y]}


def match_with_trust(template: ImageSource, *,
                     haystack: Optional[ImageSource] = None,
                     region: Optional[Sequence[int]] = None,
                     scales: Sequence[float] = (1.0,), method: str = "ccoeff_normed",
                     min_score: float = 0.0, ambiguous_ratio: float = 0.9,
                     exclude_radius: Optional[int] = None) -> Optional[TrustedMatch]:
    """Return the best match (over ``scales``) with trust metrics attached, or ``None``.

    ``is_ambiguous`` is set when the next-best peak scores at least ``ambiguous_ratio``
    times the best — a strong but untrustworthy match the caller should not blindly click.
    """
    best_match: Optional[TrustedMatch] = None
    for scale in scales:
        score_map, tmpl = _score_map(template, haystack, region=region,
                                     method=method, scale=float(scale))
        if score_map is None:
            continue
        radius = _default_radius(tmpl.shape, exclude_radius)
        (peak_x, peak_y), best, second, ratio, psr = _peak_stats(score_map, radius)
        if best < min_score or (best_match is not None and best <= best_match.score):
            continue
        best_match = TrustedMatch(int(peak_x), int(peak_y), tmpl.shape[1],
                                  tmpl.shape[0], round(best, 4), float(scale),
                                  round(second, 4), round(ratio, 4), _safe_psr(psr),
                                  ratio >= ambiguous_ratio)
    return best_match
