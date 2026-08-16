"""Will the input I send actually arrive?

Sent input can be discarded before it reaches anything, and the send call still
reports success. That is the worst failure this library has: the caller is told
"clicked (500, 300)", nothing happened, and there is no error anywhere. Two
causes, which need two different checks:

* **The workstation is locked**, or a UAC secure desktop is up. Detected by
  asking for the input desktop — a cheap, side-effect-free query.
* **Something is filtering injected input.** Anti-cheat in a foreground game
  does this. Measured on such a machine: after ``SendInput`` even
  ``GetAsyncKeyState`` does not see the key. Nothing cheap detects it —
  ``OpenInputDesktop`` succeeds, and the game's integrity level is the same
  *Medium* as ours, so a privilege comparison says everything is fine. The only
  honest test is to send a key and look.

So :func:`input_desktop_available` is free and safe to call often, while
:func:`input_reaches_system` **sends a real keystroke** and belongs on
diagnostics, not in front of every action. It uses F13, which effectively
nothing binds.

Both answer ``True`` when they cannot tell: these report a problem, and a probe
that fails must not itself become one. Imports no ``PySide6``.
"""
import sys
import time
from typing import Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

# F13. Real keyboards stop at F12, so nothing is listening for it.
PROBE_VK = 0x7C
_DESKTOP_SWITCHDESKTOP = 0x0100
_KEY_DOWN_MASK = 0x8000

# The desktop query is cheap but input primitives ask constantly; a short cache
# keeps that free without hiding a lock for long.
DESKTOP_CACHE_SEC = 2.0
_desktop_cache: Optional[Tuple[float, bool]] = None


def input_desktop_available() -> bool:
    """Whether the input desktop can receive events (not locked / secure desktop)."""
    global _desktop_cache
    if not sys.platform.startswith("win"):
        return True
    now = time.monotonic()
    if _desktop_cache and now - _desktop_cache[0] < DESKTOP_CACHE_SEC:
        return _desktop_cache[1]
    available = True
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.OpenInputDesktop.restype = ctypes.c_void_p
        user32.OpenInputDesktop.argtypes = [
            ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
        handle = user32.OpenInputDesktop(0, False, _DESKTOP_SWITCHDESKTOP)
        available = bool(handle)
        if handle:
            user32.CloseDesktop(ctypes.c_void_p(handle))
    except (OSError, AttributeError, ValueError) as error:
        autocontrol_logger.info("input desktop probe failed: %r", error)
        available = True
    _desktop_cache = (now, available)
    return available


def input_reaches_system(vk: int = PROBE_VK) -> bool:
    """Send an inert key and check the system saw it.

    **This injects a real keystroke.** Call it from a diagnostic, not before
    every action. ``True`` when the key was observed, or when the check itself
    could not run.
    """
    if not sys.platform.startswith("win"):
        return True
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        from je_auto_control.wrapper.auto_control_keyboard import (
            press_keyboard_key, release_keyboard_key,
        )
    except (OSError, ImportError, AttributeError) as error:
        autocontrol_logger.info("input reach probe unavailable: %r", error)
        return True
    try:
        user32.GetAsyncKeyState(int(vk))        # clear the sticky "was pressed" bit
        press_keyboard_key(int(vk))
        try:
            time.sleep(0.02)
            seen = bool(user32.GetAsyncKeyState(int(vk)) & _KEY_DOWN_MASK)
        finally:
            # Always release: a probe that leaves a key down is worse than no
            # probe, and the caller cannot see that it happened.
            release_keyboard_key(int(vk))
    except Exception as error:  # noqa: BLE001  # reason: a probe must not raise
        autocontrol_logger.info("input reach probe failed: %r", error)
        return True
    if not seen:
        autocontrol_logger.warning(
            "injected input is not reaching the system; something is "
            "filtering it (anti-cheat in a foreground game does this)")
    return seen
