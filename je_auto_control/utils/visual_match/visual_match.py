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
import functools
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.exception.exceptions import (
    AutoControlFlatTemplateException, AutoControlScreenException,
)

# cv2 method name -> the OpenCV constant is resolved lazily in _method().
_METHOD_NAMES = ("ccoeff_normed", "ccorr_normed", "sqdiff_normed")
ImageSource = Any


def _contain_cv2_error(fn):
    """Convert OpenCV's ``cv2.error`` into a contained AutoControlScreenException.

    A degenerate template/mask makes ``cv2.matchTemplate``/``minMaxLoc`` raise
    ``cv2.error`` — a bare ``Exception`` subclass that is NOT in the executor's
    containment tuple, so it would escape and abort the whole automation run
    instead of being recorded as a failed match step.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        import cv2
        try:
            return fn(*args, **kwargs)
        except cv2.error as error:
            raise AutoControlScreenException(
                f"{fn.__name__} failed: {error}") from error
    return wrapper


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


def _gray_code(channels: int, is_bgr: bool) -> int:
    """OpenCV colour-to-gray conversion code for the given channel order."""
    import cv2
    if channels == 4:
        return cv2.COLOR_BGRA2GRAY if is_bgr else cv2.COLOR_RGBA2GRAY
    return cv2.COLOR_BGR2GRAY if is_bgr else cv2.COLOR_RGB2GRAY


def _to_gray(source: ImageSource):
    """Load a path / ndarray / PIL image as a 2-D grayscale ndarray.

    The channel order is tracked so luminance weights stay correct: images
    read from disk via ``cv2.imread`` are BGR, while ndarray and PIL sources
    (the live ``pil_screenshot`` haystack) are RGB. Converting both with BGR
    weights would swap the R/B luminance weights, so a red template's gray
    would disagree with the same red on screen by up to ~47/255.
    """
    import cv2
    import numpy as np
    is_bgr = False
    if hasattr(source, "shape"):
        array = np.asarray(source)
    elif isinstance(source, (str, bytes)) or hasattr(source, "__fspath__"):
        array = _imread(str(source), cv2.IMREAD_COLOR)
        if array is None:
            raise ValueError(f"could not read image: {source!r}")
        is_bgr = True
    else:
        array = np.asarray(source)
    if array.ndim == 2:
        return array
    return cv2.cvtColor(array, _gray_code(array.shape[2], is_bgr))


def _grab_gray(region: Optional[Sequence[int]]):
    return _grab_gray_with_origin(region)[0]


def _grab_gray_with_origin(region: Optional[Sequence[int]]):
    """``(gray screen, origin_x, origin_y)`` in the coordinate space of the mouse.

    Goes through ``monitor_layout.grab_logical`` rather than a plain screenshot:
    that one sees only the primary monitor (so a target on a second display is
    never found) and returns physical pixels on a scaled desktop (so a matched
    point is clicked in the wrong place). The origin is what to add to an
    image-local hit — it is negative when a monitor sits left of or above the
    primary one.
    """
    from je_auto_control.utils.monitor_layout.logical_frame import grab_logical
    image, origin_x, origin_y = grab_logical(region)
    return _to_gray(image), origin_x, origin_y


def _haystack_gray(haystack: Optional[ImageSource],
                   region: Optional[Sequence[int]]):
    return _haystack_gray_with_origin(haystack, region)[0]


def _haystack_gray_with_origin(haystack: Optional[ImageSource],
                               region: Optional[Sequence[int]]):
    """``(gray haystack, origin_x, origin_y)``.

    A caller-supplied ``haystack`` is its own coordinate space, so its origin is
    ``(0, 0)`` — only a real screen grab carries a screen offset.
    """
    if haystack is not None:
        return _to_gray(haystack), 0, 0
    return _grab_gray_with_origin(region)


def _imread(path: str, flags: int):
    """Read an image file, tolerating non-ASCII paths.

    ``cv2.imread`` goes through the C locale on Windows and simply returns
    ``None`` for a path containing non-ASCII characters — indistinguishable
    from a corrupt file, and it hits anyone whose user name or folder is not
    Latin. Decoding the bytes ourselves sidesteps the filename entirely.
    """
    import cv2
    import numpy as np
    try:
        with open(path, "rb") as handle:
            buffer = np.frombuffer(handle.read(), dtype=np.uint8)
    except OSError as error:
        raise ValueError(f"could not read image: {path!r}") from error
    return cv2.imdecode(buffer, flags)


# A template with (almost) no variation breaks normalised correlation: the
# denominator is the template's variance, so as it approaches zero the whole
# score map saturates at 1.0 and the matcher "finds" the target at an arbitrary
# position. Failing outright is far better than clicking somewhere random —
# users hit this by cropping the flat inside of a button.
FLAT_TEMPLATE_STD = 1.0


def _reject_flat_template(template) -> None:
    """Raise if ``template`` is too uniform for normalised correlation."""
    import numpy as np
    if float(np.asarray(template, dtype=np.float64).std()) < FLAT_TEMPLATE_STD:
        raise AutoControlFlatTemplateException(
            "template is almost a single colour, so normalised correlation "
            "cannot locate it; crop a region with a pattern or text in it")


def _resize(template, scale: float):
    import cv2
    if abs(scale - 1.0) < 1e-9:
        return template
    height, width = template.shape[:2]
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(template, new_size)


@_contain_cv2_error
def _score_map(template: ImageSource, haystack: Optional[ImageSource] = None, *,
               region: Optional[Sequence[int]] = None,
               method: str = "ccoeff_normed", scale: float = 1.0):
    """Return ``(full correlation score map, scaled gray template)``.

    The map is oriented so higher = better for every method (``sqdiff_normed``
    is inverted). Returns ``(None, template)`` when the template is larger than
    the haystack at this scale. This exposes the whole ``matchTemplate`` surface
    that the public matchers discard, for trust / threshold / sub-pixel analysis.
    """
    import cv2
    tmpl = _resize(_to_gray(template), float(scale))
    hay = _haystack_gray(haystack, region)
    if tmpl.shape[0] > hay.shape[0] or tmpl.shape[1] > hay.shape[1]:
        return None, tmpl
    result = cv2.matchTemplate(hay, tmpl, _method(method))
    if method == "sqdiff_normed":
        result = 1.0 - result
    return result, tmpl


@_contain_cv2_error
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
    _reject_flat_template(tmpl)
    hay, origin_x, origin_y = _haystack_gray_with_origin(haystack, region)
    metric = _method(method)
    best: Optional[Match] = None
    for scale in scales:
        scaled = _resize(tmpl, float(scale))
        if scaled.shape[0] > hay.shape[0] or scaled.shape[1] > hay.shape[1]:
            continue
        _, max_val, _, max_loc = cv2.minMaxLoc(cv2.matchTemplate(hay, scaled,
                                                                 metric))
        if max_val >= min_score and (best is None or max_val > best.score):
            best = Match(int(max_loc[0]) + origin_x, int(max_loc[1]) + origin_y,
                         scaled.shape[1], scaled.shape[0],
                         round(float(max_val), 4), float(scale))
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


_NMS_CANDIDATE_FACTOR = 50
_NMS_CANDIDATE_MIN = 200


def _select_candidates(result, min_score: float, width: int, height: int,
                       max_results: int, origin: Sequence[int] = (0, 0),
                       ) -> List[Match]:
    """Candidate matches >= ``min_score``, capped to the top scorers.

    ``best_matches`` calls ``match_template_all(min_score=-1.0)``; since
    ``TM_CCOEFF_NORMED`` is in ``[-1, 1]`` that selects *every* score-map
    position — ~2M for a full screen — and materialising them all before the
    O(n·kept) Python NMS effectively hangs. Keep only the highest-scoring
    ``max_results * 50`` positions first; ordinary thresholds select far fewer,
    so this is a no-op for them.
    """
    import numpy as np
    ys, xs = np.nonzero(result >= float(min_score))
    scores = result[ys, xs]
    cap = max(int(max_results) * _NMS_CANDIDATE_FACTOR, _NMS_CANDIDATE_MIN)
    if scores.size > cap:
        top = np.argpartition(scores, scores.size - cap)[-cap:]
        xs, ys, scores = xs[top], ys[top], scores[top]
    return [Match(int(x) + int(origin[0]), int(y) + int(origin[1]),
                  width, height, round(float(s), 4), 1.0)
            for x, y, s in zip(xs, ys, scores)]


@_contain_cv2_error
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
    tmpl = _to_gray(template)
    _reject_flat_template(tmpl)
    hay, origin_x, origin_y = _haystack_gray_with_origin(haystack, region)
    height, width = tmpl.shape[:2]
    if height > hay.shape[0] or width > hay.shape[1]:
        return []
    result = cv2.matchTemplate(hay, tmpl, cv2.TM_CCOEFF_NORMED)
    candidates = _select_candidates(result, min_score, width, height,
                                    max_results, (origin_x, origin_y))
    return _nms(candidates, float(nms_iou))[:int(max_results)]


def best_matches(template: ImageSource, *,
                 haystack: Optional[ImageSource] = None,
                 region: Optional[Sequence[int]] = None,
                 top_n: int = 5) -> List[Match]:
    """Return the top ``top_n`` matches by score (any score), nearest-best first."""
    return match_template_all(template, haystack=haystack, region=region,
                              min_score=-1.0, max_results=int(top_n))


def _load_unchanged(source: ImageSource):
    """Return ``(array, is_bgr)`` keeping an alpha channel if present.

    ``is_bgr`` is True only for ``cv2.imread`` paths so the caller converts to
    gray with the correct channel order; ndarray / PIL sources are RGB.
    """
    import cv2
    import numpy as np
    if hasattr(source, "shape"):
        return np.asarray(source), False
    if isinstance(source, (str, bytes)) or hasattr(source, "__fspath__"):
        array = _imread(str(source), cv2.IMREAD_UNCHANGED)
        if array is None:
            raise ValueError(f"could not read image: {source!r}")
        return array, True
    return np.asarray(source), False


def _template_and_mask(template: ImageSource, mask: Optional[ImageSource]):
    """Return (gray_template, uint8_mask_or_None); alpha is the implicit mask."""
    import cv2
    import numpy as np
    array, is_bgr = _load_unchanged(template)
    if array.ndim == 3 and array.shape[2] == 4:
        gray = cv2.cvtColor(array, _gray_code(4, is_bgr))
        implicit = array[:, :, 3]
    elif array.ndim == 2:
        gray, implicit = array, None
    else:
        gray = cv2.cvtColor(array, _gray_code(array.shape[2], is_bgr))
        implicit = None
    chosen = _to_gray(mask) if mask is not None else implicit
    if chosen is None:
        return gray, None
    chosen = np.ascontiguousarray(chosen, dtype=np.uint8)
    if chosen.shape[:2] != gray.shape[:2]:
        raise ValueError("mask shape must match template shape")
    return gray, chosen


def _masked_scores(template: ImageSource, mask: Optional[ImageSource],
                   haystack: Optional[ImageSource],
                   region: Optional[Sequence[int]]):
    """Return (score_map, gray_template) for masked correlation, NaNs zeroed."""
    import cv2
    import numpy as np
    tmpl, msk = _template_and_mask(template, mask)
    hay = _haystack_gray(haystack, region)
    if tmpl.shape[0] > hay.shape[0] or tmpl.shape[1] > hay.shape[1]:
        return None, tmpl
    result = cv2.matchTemplate(hay, tmpl, cv2.TM_CCORR_NORMED, mask=msk)
    return np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0), tmpl


@_contain_cv2_error
def match_masked(template: ImageSource, *, mask: Optional[ImageSource] = None,
                 haystack: Optional[ImageSource] = None,
                 region: Optional[Sequence[int]] = None,
                 min_score: float = 0.9) -> Optional[Match]:
    """Return the best match counting only masked (opaque) template pixels.

    ``mask`` is a grayscale image where non-zero pixels participate; if omitted
    and ``template`` is RGBA, its alpha channel is the mask. This finds icons /
    buttons whose background is transparent or varies (a glyph over any colour)
    where a plain template would be dragged down by the irrelevant pixels.
    Returns ``None`` when nothing clears ``min_score``.
    """
    import cv2
    scores, tmpl = _masked_scores(template, mask, haystack, region)
    if scores is None:
        return None
    _, max_val, _, max_loc = cv2.minMaxLoc(scores)
    if max_val < min_score:
        return None
    return Match(int(max_loc[0]), int(max_loc[1]), tmpl.shape[1], tmpl.shape[0],
                 round(float(max_val), 4), 1.0)


@_contain_cv2_error
def match_masked_all(template: ImageSource, *, mask: Optional[ImageSource] = None,
                     haystack: Optional[ImageSource] = None,
                     region: Optional[Sequence[int]] = None,
                     min_score: float = 0.9, max_results: int = 20,
                     nms_iou: float = 0.3) -> List[Match]:
    """Return every masked match >= ``min_score`` with overlaps removed (NMS)."""
    scores, tmpl = _masked_scores(template, mask, haystack, region)
    if scores is None:
        return []
    height, width = tmpl.shape[:2]
    candidates = _select_candidates(scores, min_score, width, height,
                                    max_results)
    return _nms(candidates, float(nms_iou))[:int(max_results)]
