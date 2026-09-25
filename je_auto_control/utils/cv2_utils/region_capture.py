"""Capture a ``[left, top, right, bottom]`` screen region on whichever monitor holds it.

``pil_screenshot(screen_region=...)`` hands the box to ``ImageGrab.grab(bbox=...)``,
which on Windows captures the primary monitor only and crops that, filling
the rest with black. A colour, histogram, SSIM, contrast or colour-wait
region on any other monitor therefore measured a black image. On Windows the
region goes through ``grab_logical`` instead, which captures every monitor
in mouse coordinates as the matchers do. Elsewhere ``pil_screenshot`` already
reaches every display (macOS ``screencapture -R``, the X11 root, the Wayland
layout) and is used unchanged, as is a whole-screen capture.
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
    if not region or not sys.platform.startswith("win"):
        return pil_screenshot(screen_region=list(region) if region else None)
    _validate_region(list(region))
    from je_auto_control.utils.monitor_layout.logical_frame import grab_logical
    left, top, right, bottom = (int(value) for value in region)
    return grab_logical((left, top, right - left, bottom - top))[0]

