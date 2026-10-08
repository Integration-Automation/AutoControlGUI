"""iOS touch + key primitives via WebDriverAgent.

Every coordinate here is in **points**, WebDriverAgent's input space — not in
screenshot pixels, which are larger by the Retina scale.
:meth:`DeviceFrame.pixel_to_point` converts.
"""
from __future__ import annotations

from typing import Optional

from je_auto_control.ios.client import IOSDevice, default_ios_device, translate_device_errors


@translate_device_errors
def tap(x: int, y: int, *, device: Optional[IOSDevice] = None) -> None:
    """Single-tap at ``(x, y)`` in points."""
    handle = (device or default_ios_device()).handle
    handle.tap(int(x), int(y))


@translate_device_errors
def long_press(x: int, y: int, duration_s: float = 1.0,
               *, device: Optional[IOSDevice] = None) -> None:
    """Press-and-hold at ``(x, y)`` for ``duration_s`` seconds."""
    handle = (device or default_ios_device()).handle
    handle.tap_hold(int(x), int(y), float(duration_s))


@translate_device_errors
def swipe(x1: int, y1: int, x2: int, y2: int,
          duration_s: float = 0.5,
          *, device: Optional[IOSDevice] = None) -> None:
    """Linear swipe from ``(x1, y1)`` to ``(x2, y2)`` over ``duration_s``."""
    handle = (device or default_ios_device()).handle
    handle.swipe(int(x1), int(y1), int(x2), int(y2), float(duration_s))


@translate_device_errors
def type_text(text: str, *, device: Optional[IOSDevice] = None) -> None:
    """Type ``text`` into whatever has keyboard focus right now."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    handle = (device or default_ios_device()).handle
    handle.send_keys(text)


@translate_device_errors
def press_key(name: str, *, device: Optional[IOSDevice] = None) -> None:
    """Press a hardware/system key (``"home"``, ``"volumeup"`` …)."""
    if not name:
        raise ValueError("key name must be a non-empty string")
    handle = (device or default_ios_device()).handle
    handle.press(name)


@translate_device_errors
def drag(x1: int, y1: int, x2: int, y2: int, hold_s: float = 0.5,
         *, device: Optional[IOSDevice] = None) -> None:
    """Press at ``(x1, y1)``, hold ``hold_s`` so the item lifts, then move to ``(x2, y2)``.

    WebDriverAgent's drag takes the press duration, not the travel time.
    """
    handle = (device or default_ios_device()).handle
    handle.swipe(int(x1), int(y1), int(x2), int(y2), float(hold_s))


@translate_device_errors
def pinch(scale: float, duration_s: float = 0.5,
          *, device: Optional[IOSDevice] = None) -> None:
    """Pinch the frontmost application: ``scale`` above 1 zooms in, below 1 zooms out.

    WebDriverAgent pinches an element, not a coordinate, so the gesture is
    centred on the application rather than on a chosen point.
    """
    if scale <= 0 or scale == 1:
        raise ValueError("pinch scale must be positive and not 1")
    handle = (device or default_ios_device()).handle
    # XCTest wants scale per second, negative when the fingers close.
    velocity = (float(scale) - 1.0) / max(float(duration_s), 0.05)
    handle(className="XCUIElementTypeApplication").pinch(float(scale), velocity)


__all__ = ["drag", "long_press", "pinch", "press_key", "swipe", "tap", "type_text"]
