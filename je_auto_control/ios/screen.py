"""Screen capture + sizing for the attached iOS device."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Optional, Tuple

from je_auto_control.ios.client import (
    IOSDevice, IOSUnavailableError, default_ios_device, translate_device_errors,
)
from je_auto_control.wrapper.device_frame import (
    ORIENTATION_LANDSCAPE_LEFT, ORIENTATION_LANDSCAPE_RIGHT, ORIENTATION_PORTRAIT,
    ORIENTATION_PORTRAIT_UPSIDE_DOWN, DeviceFrame,
)

#: WebDriverAgent's orientation names.
_ORIENTATIONS = {
    "PORTRAIT": ORIENTATION_PORTRAIT,
    "LANDSCAPE": ORIENTATION_LANDSCAPE_LEFT,
    "UIA_DEVICE_ORIENTATION_LANDSCAPERIGHT": ORIENTATION_LANDSCAPE_RIGHT,
    "UIA_DEVICE_ORIENTATION_PORTRAIT_UPSIDEDOWN": ORIENTATION_PORTRAIT_UPSIDE_DOWN,
}


@translate_device_errors
def screen_size(*, device: Optional[IOSDevice] = None) -> Tuple[int, int]:
    """Return the screen size in **points**, in the current orientation, as ``(width, height)``.

    Points are WebDriverAgent's input space; a screenshot is larger by the
    Retina scale.
    """
    handle = (device or default_ios_device()).handle
    size = handle.window_size()
    if isinstance(size, dict):
        return int(size["width"]), int(size["height"])
    return int(size[0]), int(size[1])


@translate_device_errors
def screenshot(file_path: Optional[str] = None,
               *, device: Optional[IOSDevice] = None) -> Optional[str]:
    """Capture the device screen; writes PNG to ``file_path`` when given."""
    handle = (device or default_ios_device()).handle
    if file_path is None:
        return None
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # ``wda.Client.screenshot()`` accepts a path and writes the PNG.
    handle.screenshot(str(target))
    return str(target)


def _as_image(shot: Any) -> Any:
    """A WDA screenshot (PIL image, or PNG bytes) as a loaded PIL image."""
    if hasattr(shot, "size") and hasattr(shot, "save"):
        return shot
    from PIL import Image
    try:
        image = Image.open(io.BytesIO(bytes(shot)))
        image.load()
    except (OSError, ValueError, TypeError) as error:
        raise IOSUnavailableError(
            f"WebDriverAgent did not return a screenshot: {error}") from error
    return image


@translate_device_errors
def capture_frame(*, device: Optional[IOSDevice] = None) -> DeviceFrame:
    """Capture the screen with the point size and orientation needed to tap what is found.

    WebDriverAgent takes points and returns pixels, and some builds return a
    landscape screen in the panel's portrait buffer; the frame carries the
    mapping and is turned upright.
    """
    target = device or default_ios_device()
    handle = target.handle
    image = _as_image(handle.screenshot())
    orientation = _ORIENTATIONS.get(str(getattr(handle, "orientation", "PORTRAIT")),
                                    ORIENTATION_PORTRAIT)
    return DeviceFrame.from_capture(
        image, screen_size(device=target), orientation=orientation,
        platform="ios", device_id=target.url)


__all__ = ["capture_frame", "screen_size", "screenshot"]
