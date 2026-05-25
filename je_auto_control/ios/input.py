"""iOS touch + key primitives via WebDriverAgent."""
from __future__ import annotations

from typing import Optional

from je_auto_control.ios.client import IOSDevice, default_ios_device


def tap(x: int, y: int, *, device: Optional[IOSDevice] = None) -> None:
    """Single-tap absolute pixel coordinates."""
    handle = (device or default_ios_device()).handle
    handle.tap(int(x), int(y))


def long_press(x: int, y: int, duration_s: float = 1.0,
               *, device: Optional[IOSDevice] = None) -> None:
    """Press-and-hold at ``(x, y)`` for ``duration_s`` seconds."""
    handle = (device or default_ios_device()).handle
    handle.tap_hold(int(x), int(y), float(duration_s))


def swipe(x1: int, y1: int, x2: int, y2: int,
          duration_s: float = 0.5,
          *, device: Optional[IOSDevice] = None) -> None:
    """Linear swipe from ``(x1, y1)`` to ``(x2, y2)`` over ``duration_s``."""
    handle = (device or default_ios_device()).handle
    handle.swipe(int(x1), int(y1), int(x2), int(y2), float(duration_s))


def type_text(text: str, *, device: Optional[IOSDevice] = None) -> None:
    """Type ``text`` into whatever has keyboard focus right now."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    handle = (device or default_ios_device()).handle
    handle.send_keys(text)


def press_key(name: str, *, device: Optional[IOSDevice] = None) -> None:
    """Press a hardware/system key (``"home"``, ``"volumeup"`` …)."""
    if not name:
        raise ValueError("key name must be a non-empty string")
    handle = (device or default_ios_device()).handle
    handle.press(name)


__all__ = ["long_press", "press_key", "swipe", "tap", "type_text"]
