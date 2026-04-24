"""macOS hotkey backend using ``CGEventTap`` from Quartz.

Requires Accessibility permission (System Settings → Privacy & Security →
Accessibility) for the Python interpreter or the host application. Without
it ``CGEventTapCreate`` silently returns ``None`` and we log + exit.
"""
from typing import Dict, Optional, Tuple

from je_auto_control.utils.hotkey.backends.base import HotkeyBackend
from je_auto_control.utils.hotkey.hotkey_daemon import (
    BackendContext, split_combo,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_MACOS_POLL_SECONDS = 0.1

# Carbon virtual key codes for non-character keys.
_KEY_NAME_TO_KEYCODE = {
    "return": 36, "enter": 36, "tab": 48, "space": 49, "escape": 53, "esc": 53,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "insert": 114, "delete": 117,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}

# a-z -> Carbon virtual key codes.
_LETTER_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "o": 31, "u": 32, "i": 34, "p": 35, "l": 37,
    "j": 38, "k": 40, "n": 45, "m": 46,
}

# 0-9 -> Carbon virtual key codes (note the unusual ordering).
_DIGIT_KEYCODES = {
    "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22,
    "7": 26, "8": 28, "9": 25, "0": 29,
}

_FLAG_SHIFT = 1 << 17
_FLAG_CONTROL = 1 << 18
_FLAG_ALT = 1 << 19
_FLAG_CMD = 1 << 20
_FLAG_MASK_ALL = _FLAG_SHIFT | _FLAG_CONTROL | _FLAG_ALT | _FLAG_CMD


def _primary_key_to_keycode(primary: str) -> int:
    lowered = primary.lower()
    if lowered in _KEY_NAME_TO_KEYCODE:
        return _KEY_NAME_TO_KEYCODE[lowered]
    if lowered in _LETTER_KEYCODES:
        return _LETTER_KEYCODES[lowered]
    if lowered in _DIGIT_KEYCODES:
        return _DIGIT_KEYCODES[lowered]
    raise ValueError(f"unsupported hotkey key: {primary!r}")


def _combo_to_macos(combo: str) -> Tuple[int, int]:
    """Return ``(flags_mask, keycode)`` for ``combo`` on macOS."""
    mods, primary = split_combo(combo)
    mask = 0
    if "ctrl" in mods:
        mask |= _FLAG_CONTROL
    if "shift" in mods:
        mask |= _FLAG_SHIFT
    if "alt" in mods:
        mask |= _FLAG_ALT
    if "win" in mods:
        mask |= _FLAG_CMD
    return mask, _primary_key_to_keycode(primary)


class MacOSHotkeyBackend(HotkeyBackend):
    """Carbon CGEventTap-based listener. Consumes key events that match."""

    name = "macos"

    def __init__(self) -> None:
        # binding_id -> (combo, flags_mask, keycode)
        self._registered: Dict[str, Tuple[str, int, int]] = {}
        self._pending_fires: list = []

    def run_forever(self, context: BackendContext) -> None:
        try:
            import Quartz  # noqa: F401  # reason: verifying pyobjc present
        except ImportError as error:
            autocontrol_logger.error("Quartz unavailable: %r", error)
            return
        self._loop(context)

    def _loop(self, context: BackendContext) -> None:
        import Quartz
        from CoreFoundation import (
            CFRunLoopRunInMode, kCFRunLoopDefaultMode,
        )

        def tap_callback(_proxy, _event_type, event, _refcon):
            keycode = Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode,
            )
            flags = int(Quartz.CGEventGetFlags(event)) & _FLAG_MASK_ALL
            hit = self._match(keycode, flags)
            if hit is None:
                return event
            self._pending_fires.append(hit)
            return None  # consume

        mask = 1 << Quartz.kCGEventKeyDown
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGHIDEventTap, Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault, mask, tap_callback, None,
        )
        if tap is None:
            autocontrol_logger.error(
                "CGEventTapCreate returned None — enable Accessibility perms",
            )
            return
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        run_loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(
            run_loop, source, kCFRunLoopDefaultMode,
        )
        Quartz.CGEventTapEnable(tap, True)

        try:
            while not context.stop_event.is_set():
                self._sync(context.get_bindings())
                CFRunLoopRunInMode(
                    kCFRunLoopDefaultMode, _MACOS_POLL_SECONDS, True,
                )
                self._drain_fires(context.fire)
        finally:
            Quartz.CGEventTapEnable(tap, False)
            Quartz.CFRunLoopRemoveSource(
                run_loop, source, kCFRunLoopDefaultMode,
            )

    def _sync(self, bindings) -> None:
        current_ids = {b.binding_id for b in bindings}
        for stale in [bid for bid in self._registered if bid not in current_ids]:
            self._registered.pop(stale, None)
        for binding in bindings:
            prior = self._registered.get(binding.binding_id)
            if prior is not None and prior[0] == binding.combo:
                continue
            try:
                mask, keycode = _combo_to_macos(binding.combo)
            except ValueError as error:
                autocontrol_logger.error(
                    "hotkey parse failed for %s: %r", binding.combo, error,
                )
                continue
            self._registered[binding.binding_id] = (
                binding.combo, mask, keycode,
            )

    def _match(self, keycode: int, flags: int) -> Optional[str]:
        for bid, (_combo, mask, kc) in self._registered.items():
            if kc == keycode and (flags & _FLAG_MASK_ALL) == mask:
                return bid
        return None

    def _drain_fires(self, fire) -> None:
        while self._pending_fires:
            fire(self._pending_fires.pop(0))
