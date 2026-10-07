"""Unicode-safe SDK text and native-point Android gesture dispatch."""
from __future__ import annotations

from typing import Optional

from je_auto_control.android.client import UIAutomatorDevice, default_ui_device, translate_device_errors
from je_auto_control.wrapper._mobile_binding import resolve_client
from je_auto_control.wrapper._mobile_models import DeviceSessionError
from je_auto_control.wrapper.mobile_gesture import Gesture


@translate_device_errors
def type_text(text: str, *, device: Optional[UIAutomatorDevice] = None) -> None:
    """Send exact Unicode through the SDK's IME/clipboard path, never adb input text."""
    if not isinstance(text, str) or '\x00' in text:
        raise DeviceSessionError('mobile text must be a string without NUL')
    handle = (resolve_client('android', 'uiautomator2', device) or default_ui_device()).handle
    handle.send_keys(text)


@translate_device_errors
def perform_gesture(gesture: Gesture, *, device: Optional[UIAutomatorDevice] = None) -> None:
    """Send tap/hold/drag/swipe or a simultaneous two-pointer gesture via SDK RPC."""
    if not isinstance(gesture, Gesture):
        raise DeviceSessionError('perform requires a validated Gesture')
    handle = (resolve_client('android', 'uiautomator2', device) or default_ui_device()).handle
    points = [tuple(int(value) for value in point) for point in gesture.points]
    if gesture.kind == 'pinch':
        _pinch(handle, points, gesture.duration_s)
    elif gesture.kind == 'tap':
        handle.click(*points[0])
    elif gesture.kind == 'long_press':
        handle.long_click(*points[0], gesture.duration_s)
    else:
        operation = handle.drag if gesture.kind == 'drag' else handle.swipe
        operation(*points[0], *points[1], gesture.duration_s)


def _pinch(handle, points: list[tuple[int, ...]], duration: float) -> None:
    params = [{'mask': 0}, *[{'x': x, 'y': y} for x, y in points], max(2, int(duration * 200))]
    if handle.jsonrpc_call('gesture', params) is False:
        raise DeviceSessionError('Android backend rejected the two-pointer gesture')


__all__ = ['perform_gesture', 'type_text']
