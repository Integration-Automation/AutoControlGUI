"""Wayland keyboard backend (ydotool + wtype CLI bridges).

Each function delegates to one of the two Wayland-native helpers:

* **wtype** for ``type_text`` (Unicode-aware, no key-code juggling);
* **ydotool** for per-key press / release / hotkey since wtype lacks a
  hold-mode API.

Subprocess invocations are validated and never touch a shell. Missing
binaries surface as :class:`AutoControlException` with an actionable
install hint, so the operator can either install the tool or set
``JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11`` to fall back to XWayland.
"""
from __future__ import annotations

import subprocess  # nosec B404  # reason: argv-list, no shell interpolation
import time
from typing import Iterable

from je_auto_control.linux_wayland._detect import (
    WAYLAND_WTYPE, WAYLAND_YDOTOOL, binary_path,
)
from je_auto_control.linux_wayland._select_input import emitted
from je_auto_control.linux_wayland._ydotool_cli import reject_legacy_cli
from je_auto_control.utils.exception.exceptions import AutoControlException


_INSTALL_HINT_WTYPE = (
    "wtype is required for Wayland keyboard input. "
    "Install with your package manager (e.g. `apt install wtype`)."
)
_INSTALL_HINT_YDOTOOL = (
    "ydotool 1.0 or newer is required for Wayland key events. "
    "Install it with your package manager (Arch: `pacman -S ydotool`; "
    "Fedora: `dnf install ydotool`; Debian: from unstable — trixie ships no "
    "package and bookworm's 0.1.8 is too old) and ensure ydotoold is running "
    "with /dev/uinput permission."
)


def _require(name: str, hint: str) -> str:
    path = binary_path(name)
    if path is None:
        raise AutoControlException(hint)
    return path


def _require_ydotool() -> str:
    """Resolve ydotool, refusing the 0.1.x CLI that fails silently."""
    return reject_legacy_cli(_require(WAYLAND_YDOTOOL, _INSTALL_HINT_YDOTOOL))


def _run(argv: list, *, timeout: float = 5.0) -> None:
    # argv comes from a private allow-list (wtype / ydotool absolute
    # paths via shutil.which), never user input; no shell=True.
    try:
        subprocess.run(  # nosec B603  # nosemgrep
            argv, check=True, timeout=timeout,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as error:
        message = (error.stderr or b"").decode("utf-8", errors="replace")
        raise AutoControlException(
            f"{argv[0]} exited {error.returncode}: {message.strip()}",
        ) from error
    except subprocess.TimeoutExpired as error:
        raise AutoControlException(
            f"{argv[0]} timed out after {timeout}s",
        ) from error


def press_key(keycode: int) -> None:
    """Press one evdev key code. Uses libei when available, ydotool otherwise."""
    _validate_keycode(keycode)
    libei = _try_libei()
    if libei is not None and emitted(
            libei, lambda device: device.press_key(int(keycode))):
        return
    time.sleep(0.01)
    _run([_require_ydotool(), "key", f"{int(keycode)}:1"])


def release_key(keycode: int) -> None:
    """Release one evdev key code. Uses libei when available, ydotool otherwise."""
    _validate_keycode(keycode)
    libei = _try_libei()
    if libei is not None and emitted(
            libei, lambda device: device.release_key(int(keycode))):
        return
    time.sleep(0.01)
    _run([_require_ydotool(), "key", f"{int(keycode)}:0"])


def _try_libei():
    """Return a connected :class:`LibeiBackend`, or None when CLI should win."""
    try:
        from je_auto_control.linux_wayland._select_input import active_backend
        return active_backend()
    except (ImportError, RuntimeError, OSError):
        return None


def type_keyboard(keycode: int) -> None:
    """Press + release one key (a single keystroke)."""
    press_key(keycode)
    release_key(keycode)


def hotkey(keycodes: Iterable[int]) -> None:
    """Chord: press every keycode in order, then release in reverse."""
    codes = [int(code) for code in keycodes]
    if not codes:
        raise ValueError("hotkey requires at least one keycode")
    libei = _try_libei()
    if libei is not None and _libei_chord(libei, codes):
        return
    args = [_require_ydotool(), "key"]
    args.extend(f"{code}:1" for code in codes)
    args.extend(f"{code}:0" for code in reversed(codes))
    _run(args)


def _libei_chord(libei, codes: list) -> bool:
    """Send a whole chord through libei; False means the CLI has to redo it.

    Whatever went down is released in reverse before giving up, so a refusal
    part-way through cannot leave a modifier held. The CLI then replays the
    chord from a clean state — and if it was a *release* that was refused,
    replaying is also what unsticks the key.
    """
    pressed = []
    taken = True
    for code in codes:
        if not emitted(libei, lambda device, key=code: device.press_key(key)):
            taken = False
            break
        pressed.append(code)
    for code in reversed(pressed):
        if not emitted(libei,
                       lambda device, key=code: device.release_key(key)):
            taken = False
    return taken


def write(text: str) -> None:
    """Type a UTF-8 string via wtype (Unicode-aware, no key-code conversion)."""
    if not isinstance(text, str):
        raise ValueError("write requires a string")
    if not text:
        return
    _run([_require(WAYLAND_WTYPE, _INSTALL_HINT_WTYPE), "--", text])


def send_key_event_to_window(window_id: int, keycode: int) -> None:
    """Wayland has no per-window event injection. Raise explicitly."""
    raise NotImplementedError(
        "Wayland forbids per-window key injection (no XSendEvent "
        "equivalent). Focus the target window first then call "
        "press_key / type_keyboard, or use the X11 backend.",
    )


def _validate_keycode(keycode: int) -> None:
    if not isinstance(keycode, int):
        raise ValueError("Keycode must be an integer evdev code")
    if keycode <= 0:
        raise ValueError(f"Keycode must be positive, got {keycode}")


__all__ = [
    "hotkey", "press_key", "release_key", "send_key_event_to_window",
    "type_keyboard", "write",
]
