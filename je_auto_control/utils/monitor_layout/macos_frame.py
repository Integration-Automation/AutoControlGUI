"""Build the macOS capture frame in points, across every display.

``ImageGrab.grab()`` runs ``screencapture -x`` on macOS, which has two
properties the rest of the package cannot work with:

* it captures the **main display only** (Pillow's ``all_screens`` is ignored on
  darwin), so a target on a second display is never found;
* a Retina display comes back at **twice its size in points**, and points are
  what Quartz mouse events take, so a hit read off the image lands at twice
  its distance from the corner.

``screencapture -R x,y,w,h`` takes a rectangle in global display coordinates —
points, negative left of or above the main display — and Pillow's
``scale_down=True`` resizes the result to the rectangle's size in points. So
the frame is built one display at a time: ask Quartz for each display's bounds
in points, capture exactly that rectangle scaled to points, and paste it where
the display sits. A region is cut the same way, piece by piece per display,
which also covers a region that spans a 1x and a 2x display.

Nothing here imports Quartz at module level, and both the display list and the
grabber are injectable, so the arithmetic is tested with fakes on any platform.
It has not been run on Retina hardware.

Imports no ``PySide6``.
"""
from typing import Any, Callable, List, Optional, Sequence, Tuple

from je_auto_control.utils.monitor_layout.logical_frame import (
    clip_region, intersect_rect,
)

Rect = Tuple[int, int, int, int]
DisplayReader = Callable[[], Sequence[Sequence[int]]]
_MAX_DISPLAYS = 32


def quartz_display_bounds() -> List[Rect]:
    """Every active display as ``(x, y, width, height)`` in points.

    Global display coordinates: the main display's top-left corner is
    ``(0, 0)``, and a display left of or above it has a negative origin. These
    are the coordinates ``CGEventCreateMouseEvent`` and ``screencapture -R``
    take.
    """
    import Quartz

    error, display_ids, count = Quartz.CGGetActiveDisplayList(_MAX_DISPLAYS, None, None)
    if error:
        return []
    bounds: List[Rect] = []
    for display_id in list(display_ids)[:int(count)]:
        rect = Quartz.CGDisplayBounds(display_id)
        bounds.append((int(rect.origin.x), int(rect.origin.y),
                       int(rect.size.width), int(rect.size.height)))
    return bounds


def _read_displays(displays: Optional[DisplayReader]) -> List[Rect]:
    """The displays with a real area, or ``[]`` when Quartz is not installed."""
    try:
        rows = (displays or quartz_display_bounds)()
    except ImportError:
        return []
    found: List[Rect] = []
    for row in rows:
        x, y, width, height = (int(value) for value in row)
        if width > 0 and height > 0:
            found.append((x, y, width, height))
    return found


def display_union(displays: Sequence[Rect]) -> Rect:
    """The bounding box of ``displays`` as ``(x, y, width, height)``."""
    left = min(rect[0] for rect in displays)
    top = min(rect[1] for rect in displays)
    right = max(rect[0] + rect[2] for rect in displays)
    bottom = max(rect[1] + rect[3] for rect in displays)
    return left, top, right - left, bottom - top


def main_display(displays: Sequence[Rect]) -> Rect:
    """The display at the global origin, which is the main one; else the first."""
    for rect in displays:
        if rect[0] == 0 and rect[1] == 0:
            return rect
    return displays[0]


def _grab_points(image_grab: Any, rect: Rect) -> Any:
    """Capture ``rect`` (points) as an image exactly ``rect`` wide and tall."""
    left, top, width, height = rect
    image = image_grab.grab(bbox=(left, top, left + width, top + height),
                            scale_down=True)
    if image.size != (width, height):
        # A grabber that ignored scale_down handed back device pixels.
        from je_auto_control.utils.monitor_layout.logical_frame import _resample
        image = image.resize((width, height), _resample())
    return image


def _stitch(image_grab: Any, box: Rect, displays: Sequence[Rect]) -> Any:
    """``box`` (points) assembled from the part of it on each display."""
    pieces = [piece for piece in (intersect_rect(box, rect) for rect in displays)
              if piece is not None]
    if len(pieces) == 1 and pieces[0] == box:
        return _grab_points(image_grab, box)
    from PIL import Image
    canvas = Image.new("RGB", (box[2], box[3]))
    for piece in pieces:
        canvas.paste(_grab_points(image_grab, piece).convert("RGB"),
                     (piece[0] - box[0], piece[1] - box[1]))
    return canvas


def grab_macos(image_grab: Any, region: Optional[Rect] = None, *,
               all_screens: bool = True,
               displays: Optional[DisplayReader] = None,
               ) -> Optional[Tuple[Any, int, int]]:
    """Capture in points: ``(image, origin_x, origin_y)``, or ``None``.

    ``None`` means the display list is unavailable (pyobjc's Quartz is not
    installed, or it reported no display) and the caller should capture the
    way it does elsewhere.

    :param image_grab: ``ImageGrab``-shaped object.
    :param region: ``(x, y, width, height)`` in points, already validated; it
        is clipped to the displays and raises ``AutoControlScreenException``
        when none of it is on one.
    :param all_screens: with no ``region``, every display or only the main one.
    :param displays: returns each display's bounds in points; the default asks
        Quartz.
    """
    found = _read_displays(displays)
    if not found:
        return None
    if region is not None:
        box = clip_region(region, display_union(found))
    elif all_screens:
        box = display_union(found)
    else:
        box = main_display(found)
    return _stitch(image_grab, box, found), box[0], box[1]
