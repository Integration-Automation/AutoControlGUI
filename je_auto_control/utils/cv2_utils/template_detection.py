"""Locate a template image on screen, in the coordinates the mouse takes.

Captures through :func:`monitor_layout.grab_logical` rather than
``ImageGrab.grab()``: the plain grab sees only the primary monitor, so a target
on a second display could never be found — the search reported "not found" for
something plainly on screen. The shared grab also returns the frame in logical
pixels, so a hit read off it can be clicked directly on a mixed-DPI desktop.
"""
from typing import Any, List, Optional, Sequence, Tuple

from je_auto_control.utils.cv2_utils.optional import require_je_open_cv
from je_auto_control.utils.monitor_layout.logical_frame import grab_logical


def _shift(box: Sequence[int], origin: Tuple[int, int]) -> List[int]:
    """Translate an image-local ``(x1, y1, x2, y2)`` box into screen coordinates."""
    origin_x, origin_y = origin
    return [int(value) + (origin_x if index % 2 == 0 else origin_y)
            for index, value in enumerate(box)]


def _shift_result(result: Any, origin: Tuple[int, int], multi: bool) -> Any:
    """Translate a ``(found, box…)`` result, passing other shapes through.

    ``je_open_cv`` returns ``(found, box)`` normally but a different shape when
    asked to draw markers (and, on the multi path, an image-first tuple). Only
    the coordinate-bearing shape is translated; anything else is returned
    untouched rather than guessed at.
    """
    if not (isinstance(result, (tuple, list)) and len(result) >= 2
            and isinstance(result[0], bool)):
        return result
    found, boxes = result[0], result[1]
    if not found or not boxes:
        return result
    moved = ([_shift(box, origin) for box in boxes] if multi
             else _shift(boxes, origin))
    return [found, moved, *result[2:]]


def find_image(image: Any, detect_threshold: float = 1.0,
               draw_image: bool = False,
               all_screens: bool = True,
               screen_region: Optional[Sequence[int]] = None) -> List[Any]:
    """
    Find a single image on the screen using template detection.
    使用模板匹配在螢幕上尋找單一影像

    :param image: Template image 模板影像 (要尋找的影像)
    :param detect_threshold: Detection precision (0.0 ~ 1.0, 1.0 = 完全相同)
    :param draw_image: Whether to draw detection markers 是否在回傳影像上標記偵測結果
    :param all_screens: Search every monitor 是否搜尋所有螢幕
    :param screen_region: Limit the search to (x, y, width, height) 限定搜尋範圍
    :return: [found, [x1, y1, x2, y2]] 座標為螢幕座標
    """
    template_detection = require_je_open_cv()
    grab_image, origin_x, origin_y = grab_logical(
        screen_region, all_screens=all_screens)
    result = template_detection.find_object(
        image=grab_image,
        template=image,
        detect_threshold=detect_threshold,
        draw_image=draw_image
    )
    return _shift_result(result, (origin_x, origin_y), multi=False)


def find_image_multi(image: Any, detect_threshold: float = 1.0,
                     draw_image: bool = False,
                     all_screens: bool = True,
                     screen_region: Optional[Sequence[int]] = None) -> List[Any]:
    """
    Find multiple occurrences of an image on the screen using template detection.
    使用模板匹配在螢幕上尋找多個影像

    :param image: Template image 模板影像 (要尋找的影像)
    :param detect_threshold: Detection precision (0.0 ~ 1.0, 1.0 = 完全相同)
    :param draw_image: Whether to draw detection markers 是否在回傳影像上標記偵測結果
    :param all_screens: Search every monitor 是否搜尋所有螢幕
    :param screen_region: Limit the search to (x, y, width, height) 限定搜尋範圍
    :return: [found, [[x1, y1, x2, y2], ...]] 座標為螢幕座標
    """
    template_detection = require_je_open_cv()
    grab_image, origin_x, origin_y = grab_logical(
        screen_region, all_screens=all_screens)
    result = template_detection.find_multi_object(
        image=grab_image,
        template=image,
        detect_threshold=detect_threshold,
        draw_image=draw_image
    )
    return _shift_result(result, (origin_x, origin_y), multi=True)
