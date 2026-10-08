"""Capture a ``[left, top, right, bottom]`` screen region on whichever monitor holds it.

``pil_screenshot(screen_region=...)`` hands the box to ``ImageGrab.grab(bbox=...)``,
which on Windows captures the primary monitor only and crops that, filling
the rest with black. A colour, histogram, SSIM, contrast or colour-wait
region on any other monitor therefore measured a black image. On Windows the
region goes through ``grab_logical`` instead, which captures every monitor
in mouse coordinates as the matchers do.

On macOS ``screencapture -R`` reaches every display, but a Retina region
comes back at twice its size in points, the unit the mouse takes, so a blob
found in it was placed twice as far from the region's corner. The region is
grabbed with ``scale_down=True``, which keeps it in points. Elsewhere (the X11
root, the Wayland layout) and for a whole-screen capture ``pil_screenshot``
is used unchanged.
"""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Optional, Sequence

if TYPE_CHECKING:
    from PIL import Image


def grab_windows_region(left: int, top: int, right: int, bottom: int,
                        grabber: Optional[Any] = None) -> Image.Image:
    """The Windows capture of ``[left, top, right, bottom]``, on any monitor.

    Always ``right - left`` by ``bottom - top``: ``grab_logical`` clips the
    region to the desktop, and the part that is off screen is padded back in
    black here, so a point in the image is still ``(left, top)`` plus its
    position. A region with none of it on screen raises
    ``AutoControlScreenException``.
    """
    from je_auto_control.utils.monitor_layout.logical_frame import grab_logical
    width, height = right - left, bottom - top
    image, origin_x, origin_y = grab_logical((left, top, width, height), grabber=grabber)
    if image.size == (width, height):
        return image
    from PIL import Image
    canvas = Image.new(image.mode, (width, height))
    canvas.paste(image, (origin_x - left, origin_y - top))
    return canvas


def grab_screen_region(region: Optional[Sequence[int]] = None) -> Image.Image:
    """Return the screen inside ``[left, top, right, bottom]`` as a PIL image.

    ``None`` (or an empty region) captures the primary screen, as
    ``pil_screenshot()`` does. A region with no area raises
    ``AutoControlScreenException``.
    """
    from je_auto_control.utils.cv2_utils.screenshot import _validate_region, pil_screenshot
    if not region:
        return pil_screenshot(screen_region=None)
    _validate_region(list(region))
    left, top, right, bottom = (int(value) for value in region)
    if sys.platform.startswith("win"):
        return grab_windows_region(left, top, right, bottom)
    if sys.platform == "darwin":
        from je_auto_control.utils.cv2_utils.screen_grabber import image_grabber
        return image_grabber().grab(bbox=(left, top, right, bottom), scale_down=True)
    return pil_screenshot(screen_region=[left, top, right, bottom])
