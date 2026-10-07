"""iOS touch + key primitives via WebDriverAgent."""
from __future__ import annotations

from typing import Optional

from je_auto_control.wrapper._mobile_binding import resolve_client
from je_auto_control.wrapper._mobile_models import DeviceSessionError
from je_auto_control.wrapper.mobile_gesture import Gesture

from je_auto_control.ios.client import IOSDevice, default_ios_device, translate_device_errors


@translate_device_errors
def tap(x: int, y: int, *, device: Optional[IOSDevice] = None) -> None:
    """Single-tap native UIKit points; legacy numeric behavior is unchanged."""
    handle = (resolve_client('ios', 'wda', device) or default_ios_device()).handle
    handle.tap(int(x), int(y))


@translate_device_errors
def long_press(x: int, y: int, duration_s: float = 1.0,
               *, device: Optional[IOSDevice] = None) -> None:
    """Press-and-hold at ``(x, y)`` for ``duration_s`` seconds."""
    handle = (resolve_client('ios', 'wda', device) or default_ios_device()).handle
    handle.tap_hold(int(x), int(y), float(duration_s))


@translate_device_errors
def swipe(x1: int, y1: int, x2: int, y2: int,
          duration_s: float = 0.5,
          *, device: Optional[IOSDevice] = None) -> None:
    """Linear swipe from ``(x1, y1)`` to ``(x2, y2)`` over ``duration_s``."""
    handle = (resolve_client('ios', 'wda', device) or default_ios_device()).handle
    handle.swipe(int(x1), int(y1), int(x2), int(y2), float(duration_s))


@translate_device_errors
def type_text(text: str, *, device: Optional[IOSDevice] = None) -> None:
    """Type ``text`` into whatever has keyboard focus right now."""
    if not isinstance(text, str):
        raise TypeError('text must be a string')
    if '\x00' in text:
        raise DeviceSessionError('mobile text must be a string without NUL')
    handle = (resolve_client('ios', 'wda', device) or default_ios_device()).handle
    handle.send_keys(text)


@translate_device_errors
def press_key(name: str, *, device: Optional[IOSDevice] = None) -> None:
    """Press a hardware/system key (``"home"``, ``"volumeup"`` …)."""
    if not name:
        raise ValueError("key name must be a non-empty string")
    handle = (resolve_client('ios', 'wda', device) or default_ios_device()).handle
    handle.press(name)


@translate_device_errors
def perform_gesture(gesture: Gesture, *, device: Optional[IOSDevice] = None) -> None:
    """Use WDA native points; pinch requires its W3C simultaneous-touch endpoint."""
    if not isinstance(gesture, Gesture):
        raise DeviceSessionError('perform requires a validated Gesture')
    handle = (resolve_client('ios', 'wda', device) or default_ios_device()).handle
    points = [(int(point[0]), int(point[1])) for point in gesture.points]
    if gesture.kind == 'pinch':
        actions = [_pointer(index, points[index], points[index + 2], gesture.duration_s) for index in range(2)]
        # pylint: disable-next=protected-access  # reason: owned transport bounds the explicit W3C actions request
        handle._fetch('POST', '/actions', {'actions': actions}, with_session=True)
    elif gesture.kind == 'tap':
        handle.tap(*points[0])
    elif gesture.kind == 'long_press':
        handle.tap_hold(*points[0], gesture.duration_s)
    else:
        handle.swipe(*points[0], *points[1], gesture.duration_s)


def _pointer(index: int, start: tuple[int, int], end: tuple[int, int], duration: float) -> dict:
    return {'type': 'pointer', 'id': f'finger-{index}', 'parameters': {'pointerType': 'touch'}, 'actions': [
        {'type': 'pointerMove', 'duration': 0, 'origin': 'viewport', 'x': start[0], 'y': start[1]},
        {'type': 'pointerDown', 'button': 0},
        {'type': 'pointerMove', 'duration': max(1, int(duration * 1000)), 'origin': 'viewport',
         'x': end[0], 'y': end[1]},
        {'type': 'pointerUp', 'button': 0},
    ]}


__all__ = ["long_press", "perform_gesture", "press_key", "swipe", "tap", "type_text"]
