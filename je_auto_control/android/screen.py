"""Android screen geometry and capture as a :class:`DeviceFrame`.

``input tap`` takes coordinates in the display's *current* orientation, and on
current Android ``screencap`` returns the image in that same orientation, so a
located pixel is the tap coordinate. That is checked rather than assumed: the
display size and rotation are read from the device, and a screenshot that came
back in the panel's natural orientation instead is turned upright before
anything is located in it.
"""
from __future__ import annotations

import io
import re
from typing import Any, Optional, Tuple

from je_auto_control.android.adb_client import AdbError
from je_auto_control.wrapper.device_frame import ORIENTATIONS, DeviceFrame

_SIZE = re.compile(r"(Override|Physical) size:\s*(\d+)x(\d+)")
_SURFACE_ORIENTATION = re.compile(r"SurfaceOrientation:\s*(\d)")


def display_size(adb: Any) -> Optional[Tuple[int, int]]:
    """The display size in its natural orientation, honouring a ``wm size`` override."""
    sizes = {kind: (int(width), int(height))
             for kind, width, height in _SIZE.findall(adb.shell("wm size"))}
    return sizes.get("Override") or sizes.get("Physical")


def display_rotation(adb: Any) -> int:
    """Quarter turns the display is rotated from natural (``Surface.ROTATION_*``), 0 if unknown."""
    found = _SURFACE_ORIENTATION.search(adb.shell("dumpsys input"))
    return int(found.group(1)) % 4 if found else 0


def capture_frame(adb: Any, device_id: str = "") -> DeviceFrame:
    """Capture the screen with the geometry needed to tap what is found in it."""
    from PIL import Image
    data = adb.screencap_png()
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (OSError, ValueError) as error:
        raise AdbError(f"adb screencap did not return an image: {error}") from error
    rotation = display_rotation(adb)
    natural = display_size(adb)
    if natural is None:
        # No geometry to check against: the screenshot is the coordinate space.
        return DeviceFrame(image=image, point_size=image.size, platform="android",
                           device_id=device_id)
    point_size = (natural[1], natural[0]) if rotation % 2 else natural
    return DeviceFrame.from_capture(
        image, point_size, orientation=ORIENTATIONS[rotation],
        platform="android", device_id=device_id)


__all__ = ["capture_frame", "display_rotation", "display_size"]
