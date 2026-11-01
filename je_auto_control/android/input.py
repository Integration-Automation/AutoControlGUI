"""Android text and gestures that say so when the device cannot receive them.

``adb shell input text`` maps characters through the device's key character
map: it carries printable ASCII and nothing else, and it reports success
either way. ``adb shell input`` also has no multi-touch. This module picks a
path that can really deliver what was asked — the ADBKeyBoard IME or the
uiautomator2 daemon — and raises when there is none, instead of sending
something else and returning.
"""
from __future__ import annotations

import base64
import shlex
from importlib.util import find_spec
from typing import Any, Optional, Tuple

from je_auto_control.android.adb_client import (
    AdbError, AdbUnsupportedError, adb_text_safe,
)
from je_auto_control.android.client import UIAutomatorDevice, translate_device_errors
from je_auto_control.wrapper.device_context import Drag, LongPress, Pinch, Swipe, Tap

#: The IME of the ADBKeyBoard project, which accepts text as a broadcast.
ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
#: uiautomator injects a two-pointer gesture in steps of about 5 ms.
_STEPS_PER_SECOND = 200


def current_input_method(adb: Any) -> str:
    """The id of the device's selected IME. A settings read: no input is sent."""
    return str(adb.shell("settings get secure default_input_method")).strip()


def _ui_device_for(adb: Any, ui_device: Optional[UIAutomatorDevice]) -> Optional[UIAutomatorDevice]:
    """The uiautomator2 wrapper to use: the given one, else a new one if the SDK is installed."""
    if ui_device is not None:
        return ui_device
    if find_spec("uiautomator2") is None:
        return None
    return UIAutomatorDevice(serial=getattr(adb, "default_serial", None))


def _broadcast_text(adb: Any, text: str) -> None:
    """Hand ``text`` to the selected ADBKeyBoard IME as base64."""
    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    out = adb.shell("am broadcast -a ADB_INPUT_B64 --es msg " + shlex.quote(payload))
    if "Broadcast completed" not in out:
        raise AdbError("the ADBKeyBoard broadcast was not delivered")


@translate_device_errors
def _send_keys(ui_device: UIAutomatorDevice, text: str) -> None:
    ui_device.handle.send_keys(text)


def type_text(adb: Any, text: str, *,
              ui_device: Optional[UIAutomatorDevice] = None) -> None:
    """Type ``text`` into the focused field through a path that can carry it.

    Printable ASCII goes through ``adb shell input text``. Anything else goes
    to the ADBKeyBoard IME when it is the selected input method, else to
    uiautomator2 when it is installed. With neither, this raises
    :class:`AdbUnsupportedError`: nothing is sent, because ``input text`` would
    drop the characters and still exit 0.
    """
    if not isinstance(text, str):
        raise AdbError(f"text must be a string, got {type(text).__name__}")
    if not text:
        return
    if adb_text_safe(text):
        adb.text(text)
        return
    if current_input_method(adb) == ADB_KEYBOARD_IME:
        _broadcast_text(adb, text)
        return
    chosen = _ui_device_for(adb, ui_device)
    if chosen is None:
        raise AdbUnsupportedError(
            "this text has characters `adb shell input text` cannot deliver, and "
            "neither Unicode path is available",
            reason="non-ASCII text needs the ADBKeyBoard IME selected on the device "
                   "or uiautomator2 installed on the host",
            alternative="pip install uiautomator2, or install ADBKeyBoard and run "
                        f"`adb shell ime set {ADB_KEYBOARD_IME}`")
    _send_keys(chosen, text)


def tap(adb: Any, gesture: Tap) -> None:
    """Tap."""
    adb.tap(gesture.x, gesture.y)


def long_press(adb: Any, gesture: LongPress) -> None:
    """Hold in place: a swipe that does not move."""
    adb.swipe(gesture.x, gesture.y, gesture.x, gesture.y,
              duration_ms=max(1, round(gesture.duration_s * 1000)))


def swipe(adb: Any, gesture: Swipe) -> None:
    """Swipe."""
    adb.swipe(gesture.x1, gesture.y1, gesture.x2, gesture.y2,
              duration_ms=max(1, round(gesture.duration_s * 1000)))


@translate_device_errors
def _ui_drag(ui_device: UIAutomatorDevice, gesture: Drag) -> None:
    ui_device.handle.drag(gesture.x1, gesture.y1, gesture.x2, gesture.y2,
                          duration=float(gesture.hold_s + gesture.duration_s))


def drag(adb: Any, gesture: Drag, *,
         ui_device: Optional[UIAutomatorDevice] = None) -> None:
    """Drag and drop.

    ``input draganddrop`` holds before it moves, which is what lifts an item;
    a device whose ``input`` lacks it falls back to uiautomator2, and raises
    when that is not installed either.
    """
    total_ms = max(1, round((gesture.hold_s + gesture.duration_s) * 1000))
    try:
        adb.input_command(
            f"draganddrop {int(gesture.x1)} {int(gesture.y1)} "
            f"{int(gesture.x2)} {int(gesture.y2)} {total_ms}")
    except AdbUnsupportedError:
        chosen = _ui_device_for(adb, ui_device)
        if chosen is None:
            raise
        _ui_drag(chosen, gesture)


def pinch_points(gesture: Pinch) -> Tuple[Tuple[int, int], Tuple[int, int],
                                          Tuple[int, int], Tuple[int, int]]:
    """``(start1, start2, end1, end2)`` for two fingers either side of the centre."""
    wide = gesture.span / 2.0
    narrow = wide / max(gesture.scale, 1.0 / gesture.scale)
    begin, end = (narrow, wide) if gesture.scale > 1 else (wide, narrow)
    x, y = int(gesture.x), int(gesture.y)
    return ((round(x - begin), y), (round(x + begin), y),
            (round(x - end), y), (round(x + end), y))


@translate_device_errors
def _ui_pinch(ui_device: UIAutomatorDevice, gesture: Pinch) -> None:
    start1, start2, end1, end2 = pinch_points(gesture)
    steps = max(2, round(gesture.duration_s * _STEPS_PER_SECOND))
    # A two-pointer gesture is performed on a UI object but takes absolute
    # points, so the empty selector (the root node) serves for any position.
    ui_device.handle().gesture(start1, start2, end1, end2, steps=steps)


def pinch(adb: Any, gesture: Pinch, *,
          ui_device: Optional[UIAutomatorDevice] = None) -> None:
    """Two-finger pinch. ``adb shell input`` has one pointer, so this needs uiautomator2."""
    chosen = _ui_device_for(adb, ui_device)
    if chosen is None:
        raise AdbUnsupportedError(
            "a pinch needs two pointers and `adb shell input` has one",
            reason="multi-touch needs uiautomator2 installed on the host",
            alternative="pip install uiautomator2")
    _ui_pinch(chosen, gesture)


__all__ = [
    "ADB_KEYBOARD_IME", "current_input_method", "drag", "long_press", "pinch",
    "pinch_points", "swipe", "tap", "type_text",
]
