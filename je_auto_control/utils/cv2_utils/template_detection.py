"""Locate a template image on screen, in the coordinates the mouse takes.

Captures through :func:`monitor_layout.grab_logical` rather than
``ImageGrab.grab()``: the plain grab sees only the primary monitor, so a target
on a second display could never be found — the search reported "not found" for
something plainly on screen. The shared grab also returns the frame in logical
pixels, so a hit read off it can be clicked directly on a mixed-DPI desktop.
"""
import os
from typing import Any, List, Optional, Sequence, Tuple

from je_auto_control.utils.cv2_utils.optional import require_cv2, require_je_open_cv
from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.utils.monitor_layout.logical_frame import grab_logical


def _shift(box: Sequence[int], origin: Tuple[int, int]) -> List[int]:
    """Translate an image-local ``(x1, y1, x2, y2)`` box into screen coordinates."""
    origin_x, origin_y = origin
    return [int(value) + (origin_x if index % 2 == 0 else origin_y)
            for index, value in enumerate(box)]


#: TM_CCOEFF_NORMED is computed in float32: a pixel-identical match scores
#: 0.99999905, so ``>= 1.0`` -- the default threshold -- never matched it.
_SCORE_EPSILON = 1e-5


def _prepare(image: Any, detect_threshold: float,
             screen_region: Optional[Sequence[int]],
             all_screens: bool) -> Tuple[Any, Any, float, Tuple[int, int]]:
    """Validate the inputs; return ``(scores, template, threshold, origin)``."""
    threshold = float(detect_threshold)
    if not 0.0 <= threshold <= 1.0:
        # -1 matched everything (154 "hits" on a random frame); 85, meant as a
        # percentage, could only ever report "not found".
        raise ImageNotFoundException(
            f"detect_threshold must be between 0 and 1, got {detect_threshold!r}")
    if isinstance(image, (str, os.PathLike)) and not os.path.isfile(image):
        raise ImageNotFoundException(f"template image not found: {image}")
    open_cv = require_je_open_cv()
    cv2 = require_cv2()
    grab_image, origin_x, origin_y = grab_logical(screen_region, all_screens=all_screens)
    frame, template = open_cv.image_translate(grab_image, os.fspath(image)
                                              if isinstance(image, os.PathLike) else image)
    if template is None:
        # cv2.imread returns None for an unreadable file; that used to surface
        # as "'NoneType' object has no attribute 'shape'".
        raise ImageNotFoundException(f"cannot read template image: {image}")
    if template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
        raise ImageNotFoundException("template is larger than the searched area")
    scores = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    effective = min(threshold, 1.0 - _SCORE_EPSILON)
    return (frame, scores), template, effective, (origin_x, origin_y)


def _draw(frame: Any, boxes: Sequence[Sequence[int]]) -> Any:
    cv2 = require_cv2()
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
    return frame


def find_image(image: Any, detect_threshold: float = 1.0,
               draw_image: bool = False,
               all_screens: bool = True,
               screen_region: Optional[Sequence[int]] = None) -> List[Any]:
    """
    Find a single image on the screen using template detection.
    使用模板匹配在螢幕上尋找單一影像

    The best-scoring position is returned: the first position over the
    threshold in scan order was the topmost-leftmost near miss, 1-5 pixels
    off the true match at thresholds below 1.

    :param image: Template image 模板影像 (path, PIL image or array)
    :param detect_threshold: Detection precision (0.0 ~ 1.0, 1.0 = 完全相同)
    :param draw_image: Also return the searched frame with the match marked
    :param all_screens: Search every monitor 是否搜尋所有螢幕
    :param screen_region: Limit the search to (x, y, width, height) 限定搜尋範圍
    :return: [found, [x1, y1, x2, y2]] in screen coordinates (+ the frame when drawing)
    """
    (frame, scores), template, threshold, origin = _prepare(
        image, detect_threshold, screen_region, all_screens)
    _min_score, max_score, _min_at, (left, top) = require_cv2().minMaxLoc(scores)
    height, width = template.shape[:2]
    found = bool(max_score >= threshold)
    box = [left, top, left + width, top + height] if found else []
    result: List[Any] = [found, _shift(box, origin) if found else []]
    if draw_image:
        result.append(_draw(frame, [box] if found else []))
    return result


def find_image_multi(image: Any, detect_threshold: float = 1.0,
                     draw_image: bool = False,
                     all_screens: bool = True,
                     screen_region: Optional[Sequence[int]] = None) -> List[Any]:
    """
    Find multiple occurrences of an image on the screen using template detection.
    使用模板匹配在螢幕上尋找多個影像

    Matches come best score first; a position within a template's shorter
    side of an already-accepted match is the same occurrence and is dropped.

    :param image: Template image 模板影像 (path, PIL image or array)
    :param detect_threshold: Detection precision (0.0 ~ 1.0, 1.0 = 完全相同)
    :param draw_image: Also return the searched frame with the matches marked
    :param all_screens: Search every monitor 是否搜尋所有螢幕
    :param screen_region: Limit the search to (x, y, width, height) 限定搜尋範圍
    :return: [found, [[x1, y1, x2, y2], ...]] in screen coordinates (+ the frame
        when drawing -- always found first; the draw path used to put the frame
        first, and every caller then read the frame as ``found``)
    """
    import numpy as np
    (frame, scores), template, threshold, origin = _prepare(
        image, detect_threshold, screen_region, all_screens)
    height, width = template.shape[:2]
    rows, cols = np.nonzero(scores >= threshold)
    order = np.argsort(-scores[rows, cols], kind="stable")
    spacing = min(height, width)
    accepted: List[Tuple[int, int]] = []
    for index in order:
        left, top = int(cols[index]), int(rows[index])
        if all((left - x) ** 2 + (top - y) ** 2 >= spacing ** 2 for x, y in accepted):
            accepted.append((left, top))
    boxes = [[left, top, left + width, top + height] for left, top in accepted]
    result: List[Any] = [bool(boxes), [_shift(box, origin) for box in boxes]]
    if draw_image:
        result.append(_draw(frame, boxes))
    return result
