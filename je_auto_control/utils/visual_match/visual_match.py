"""Confidence-returning template matching: score, multi-scale, find-all + NMS.

The project's template matcher (``je_open_cv.find_object`` via ``cv2_utils``) is
single-scale and returns only bounding boxes — the correlation *score* it computes
internally is discarded, so there is no way to rank candidates, set a confidence
threshold and read back how well it matched, find a button when the UI is
DPI/zoom-scaled, or enumerate *every* occurrence. This adds those, in the style of
PyAutoGUI ``confidence`` / ``locateAll`` and SikuliX ``similarity`` / ``findAll``.

The matching takes an injectable ``haystack`` image (ndarray / path / PIL), so it
is unit-testable on synthetic arrays without a real screen; only the default
(grab the screen) is device-bound. OpenCV + NumPy come in via the project's
``je_open_cv`` dependency and are imported lazily. Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

# cv2 method name -> the OpenCV constant is resolved lazily in _method().
_METHOD_NAMES = ("ccoeff_normed", "ccorr_normed", "sqdiff_normed")
ImageSource = Any


@dataclass(frozen=True)
class Match:
    """One template match: top-left (x, y), size, correlation score, scale."""

    x: int
    y: int
    width: int
    height: int
    score: float
    scale: float

    @property
    def center(self) -> List[int]:
        """The match's centre point ``[x, y]`` (ready to click)."""
        return [self.x + self.width // 2, self.y + self.height // 2]

    def to_dict(self) -> Dict[str, Any]:
        """Return the match as a plain dict including the centre point."""
        data = asdict(self)
        data["center"] = self.center
        return data


def _method(name: str) -> int:
    import cv2
    table = {"ccoeff_normed": cv2.TM_CCOEFF_NORMED,
             "ccorr_normed": cv2.TM_CCORR_NORMED,
             "sqdiff_normed": cv2.TM_SQDIFF_NORMED}
    if name not in table:
        raise ValueError(f"unknown method: {name!r}")
    return table[name]


def _to_gray(source: ImageSource):
    """Load a path / ndarray / PIL image as a 2-D grayscale ndarray."""
    import cv2
    import numpy as np
    if hasattr(source, "shape"):
        array = np.asarray(source)
    elif isinstance(source, (str, bytes)) or hasattr(source, "__fspath__"):
        array = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if array is None:
            raise ValueError(f"could not read image: {source!r}")
    else:
        array = np.asarray(source)
    if array.ndim == 2:
        return array
    channels = array.shape[2]
    code = cv2.COLOR_BGRA2GRAY if channels == 4 else cv2.COLOR_BGR2GRAY
    return cv2.cvtColor(array, code)


def _grab_gray(region: Optional[Sequence[int]]):
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    image = pil_screenshot(screen_region=list(region) if region else None)
    return _to_gray(image)


def _haystack_gray(haystack: Optional[ImageSource],
                   region: Optional[Sequence[int]]):
    return _to_gray(haystack) if haystack is not None else _grab_gray(region)


def _resize(template, scale: float):
    import cv2
    if abs(scale - 1.0) < 1e-9:
        return template
    height, width = template.shape[:2]
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(template, new_size)


def match_template(template: ImageSource, *, haystack: Optional[ImageSource] = None,
                   region: Optional[Sequence[int]] = None,
                   scales: Sequence[float] = (1.0,), min_score: float = 0.8,
                   method: str = "ccoeff_normed") -> Optional[Match]:
    """Return the single best match of ``template`` at or above ``min_score``.

    Searches each scale in ``scales`` (e.g. ``(0.9, 1.0, 1.1)`` for DPI / zoom
    tolerance) and keeps the highest-scoring hit, or ``None`` if none clear the
    threshold.
    """
    import cv2
    tmpl = _to_gray(template)
    hay = _haystack_gray(haystack, region)
    metric = _method(method)
    best: Optional[Match] = None
    for scale in scales:
        scaled = _resize(tmpl, float(scale))
        if scaled.shape[0] > hay.shape[0] or scaled.shape[1] > hay.shape[1]:
            continue
        _, max_val, _, max_loc = cv2.minMaxLoc(cv2.matchTemplate(hay, scaled,
                                                                 metric))
        if max_val >= min_score and (best is None or max_val > best.score):
            best = Match(int(max_loc[0]), int(max_loc[1]), scaled.shape[1],
                         scaled.shape[0], round(float(max_val), 4), float(scale))
    return best


def _iou(a: Match, b: Match) -> float:
    left = max(a.x, b.x)
    top = max(a.y, b.y)
    right = min(a.x + a.width, b.x + b.width)
    bottom = min(a.y + a.height, b.y + b.height)
    inter = max(0, right - left) * max(0, bottom - top)
    if inter == 0:
        return 0.0
    union = a.width * a.height + b.width * b.height - inter
    return inter / union


def _nms(matches: List[Match], iou_threshold: float) -> List[Match]:
    kept: List[Match] = []
    for candidate in sorted(matches, key=lambda m: m.score, reverse=True):
        if all(_iou(candidate, k) <= iou_threshold for k in kept):
            kept.append(candidate)
    return kept


def match_template_all(template: ImageSource, *,
                       haystack: Optional[ImageSource] = None,
                       region: Optional[Sequence[int]] = None,
                       min_score: float = 0.8, max_results: int = 20,
                       nms_iou: float = 0.3) -> List[Match]:
    """Return every match of ``template`` >= ``min_score``, overlaps removed.

    Overlapping detections (the matcher fires on neighbouring pixels) are merged
    by non-maximum suppression on the intersection-over-union, highest score
    kept. Results are ordered by score, capped at ``max_results``.
    """
    import cv2
    import numpy as np
    tmpl = _to_gray(template)
    hay = _haystack_gray(haystack, region)
    height, width = tmpl.shape[:2]
    result = cv2.matchTemplate(hay, tmpl, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.nonzero(result >= float(min_score))
    candidates = [Match(int(x), int(y), width, height,
                        round(float(result[y, x]), 4), 1.0)
                  for y, x in zip(ys, xs)]
    return _nms(candidates, float(nms_iou))[:int(max_results)]


def best_matches(template: ImageSource, *,
                 haystack: Optional[ImageSource] = None,
                 region: Optional[Sequence[int]] = None,
                 top_n: int = 5) -> List[Match]:
    """Return the top ``top_n`` matches by score (any score), nearest-best first."""
    return match_template_all(template, haystack=haystack, region=region,
                              min_score=-1.0, max_results=int(top_n))
