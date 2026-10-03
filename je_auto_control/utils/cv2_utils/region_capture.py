"""Capture a ``[left, top, right, bottom]`` screen region on whichever monitor holds it.

Windows regions go through ``grab_logical`` to reach negative monitor
coordinates instead of cropping only the primary screen.

On macOS ``screencapture -R`` reaches every display, but a Retina region
comes back at twice its size in points, the unit the mouse takes, so a blob
found in it was placed twice as far from the region's corner. The region is
normalized explicitly by ``grab_logical``, supporting older Pillow releases
without ``scale_down``. X11/Wayland regions use the same virtual-desktop
capture and clipping boundary; primary captures retain ``pil_screenshot``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from PIL import Image


def grab_screen_region(region: Optional[Sequence[int]] = None) -> Image.Image:
    """Return the screen inside ``[left, top, right, bottom]`` as a PIL image.

    ``None`` (or an empty region) captures the primary screen, as
    ``pil_screenshot()`` does. A region with no area raises
    ``AutoControlScreenException``.
    """
    return grab_screen_region_with_origin(region)[0]


def grab_screen_region_with_origin(region: Optional[Sequence[int]] = None
                                   ) -> Tuple[Image.Image, int, int]:
    """Return a capture plus its actual clipped logical desktop origin."""
    from je_auto_control.utils.cv2_utils.screenshot import _validate_region, pil_screenshot
    if not region:
        return pil_screenshot(screen_region=None), 0, 0
    _validate_region(list(region))
    left, top, right, bottom = (int(value) for value in region)
    from je_auto_control.utils.monitor_layout.logical_frame import grab_logical
    return grab_logical((left, top, right - left, bottom - top))
