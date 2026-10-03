"""Capture a ``[left, top, right, bottom]`` screen region on whichever monitor holds it.

Windows regions go through ``grab_logical`` to reach negative monitor
coordinates instead of cropping only the primary screen.

On macOS ``screencapture -R`` reaches every display, but a Retina region
comes back at twice its size in points, the unit the mouse takes, so a blob
found in it was placed twice as far from the region's corner. The region is
normalized explicitly by ``grab_logical``, supporting older Pillow releases
without ``scale_down``. Elsewhere (the X11 root, the Wayland layout) and
for a primary-screen capture ``pil_screenshot`` is used.
"""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    from PIL import Image


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
    if sys.platform.startswith("win") or sys.platform == "darwin":
        from je_auto_control.utils.monitor_layout.logical_frame import grab_logical
        return grab_logical((left, top, right - left, bottom - top))[0]
    return pil_screenshot(screen_region=[left, top, right, bottom])
