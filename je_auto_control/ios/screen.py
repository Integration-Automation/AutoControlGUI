"""Screen capture + sizing for the attached iOS device."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from je_auto_control.ios.client import IOSDevice, default_ios_device


def screen_size(*, device: Optional[IOSDevice] = None) -> Tuple[int, int]:
    """Return the device's current pixel size as ``(width, height)``."""
    handle = (device or default_ios_device()).handle
    size = handle.window_size()
    if isinstance(size, dict):
        return int(size["width"]), int(size["height"])
    return int(size[0]), int(size[1])


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


__all__ = ["screen_size", "screenshot"]
