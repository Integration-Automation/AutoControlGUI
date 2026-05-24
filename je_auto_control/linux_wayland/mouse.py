"""Wayland mouse backend via the ydotool CLI.

Wayland compositors do not let arbitrary clients move the cursor or
synthesise buttons; the ydotool daemon owns ``/dev/uinput`` and
arbitrates on our behalf. Buttons here are the BTN_* codes that
ydotool consumes (``0xC0`` left, ``0xC1`` right, ``0xC2`` middle —
ydotool's documented values for the ``click`` verb).
"""
from __future__ import annotations

import subprocess  # nosec B404  # reason: argv-list, no shell interpolation
import time
from typing import Optional, Tuple

from je_auto_control.linux_wayland._detect import WAYLAND_YDOTOOL, binary_path
from je_auto_control.utils.exception.exceptions import AutoControlException


# ydotool ``click`` accepts hex bitmasks. Hold-bit (0x40) | press (0x00).
wayland_mouse_left = 0xC0
wayland_mouse_middle = 0xC2
wayland_mouse_right = 0xC1
wayland_scroll_direction_up = 1
wayland_scroll_direction_down = -1
wayland_scroll_direction_left = -2
wayland_scroll_direction_right = 2

_INSTALL_HINT = (
    "ydotool is required for Wayland mouse input. "
    "Install with your package manager (e.g. `apt install ydotool`) "
    "and ensure ydotoold runs with /dev/uinput permission."
)


def _require_ydotool() -> str:
    path = binary_path(WAYLAND_YDOTOOL)
    if path is None:
        raise AutoControlException(_INSTALL_HINT)
    return path


def _run(argv: list, *, timeout: float = 5.0) -> None:
    # argv comes from a private allow-list (ydotool absolute path via
    # shutil.which), never user input; no shell=True.
    try:
        subprocess.run(  # nosec B603  # nosemgrep
            argv, check=True, timeout=timeout,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as error:
        message = (error.stderr or b"").decode("utf-8", errors="replace")
        raise AutoControlException(
            f"ydotool exited {error.returncode}: {message.strip()}",
        ) from error
    except subprocess.TimeoutExpired as error:
        raise AutoControlException(
            f"ydotool timed out after {timeout}s",
        ) from error


def position() -> Tuple[int, int]:
    """ydotool offers no read-back of cursor position. Raise explicitly."""
    raise NotImplementedError(
        "Wayland forbids cursor query without a screencast portal. Track "
        "the cursor in-process or use the X11 backend.",
    )


def set_position(x: int, y: int) -> None:
    """Move the cursor to absolute (x, y). Uses libei when available."""
    libei = _try_libei()
    if libei is not None:
        libei.set_position(int(x), int(y))
        return
    time.sleep(0.01)
    _run([_require_ydotool(), "mousemove", "--absolute",
          "-x", str(int(x)), "-y", str(int(y))])


def _try_libei():
    try:
        from je_auto_control.linux_wayland import select_input_backend
        if select_input_backend() != "libei":
            return None
        from je_auto_control.linux_wayland.libei import get_default_backend
        backend = get_default_backend()
        if backend is None:
            return None
        backend.connect()
        return backend
    except (ImportError, RuntimeError, OSError):
        return None


def press_mouse(mouse_keycode: int) -> None:
    """Press a mouse button (hold)."""
    time.sleep(0.01)
    _run([_require_ydotool(), "click", f"{int(mouse_keycode) | 0x40:#x}"])


def release_mouse(mouse_keycode: int) -> None:
    """Release a held mouse button."""
    time.sleep(0.01)
    _run([_require_ydotool(), "click", f"{int(mouse_keycode) & ~0x40:#x}"])


def click_mouse(mouse_keycode: int, x: Optional[int] = None,
                y: Optional[int] = None) -> None:
    """Press + release a mouse button, optionally moving first."""
    if x is not None and y is not None:
        set_position(int(x), int(y))
    time.sleep(0.01)
    _run([_require_ydotool(), "click", f"{int(mouse_keycode):#x}"])


def scroll(direction: int, x: Optional[int] = None,
           y: Optional[int] = None) -> None:
    """Scroll by ``direction`` notches (positive = up, negative = down)."""
    if x is not None and y is not None:
        set_position(int(x), int(y))
    _run([_require_ydotool(), "mousemove", "--wheel",
          "-y", str(int(direction))])


def send_mouse_event_to_window(*_args, **_kwargs) -> None:
    """Wayland has no per-window mouse injection."""
    raise NotImplementedError(
        "Wayland forbids per-window mouse injection (no XSendEvent "
        "equivalent). Focus the window first, then call click_mouse, "
        "or use the X11 backend.",
    )


__all__ = [
    "click_mouse", "position", "press_mouse", "release_mouse",
    "scroll", "send_mouse_event_to_window", "set_position",
    "wayland_mouse_left", "wayland_mouse_middle", "wayland_mouse_right",
    "wayland_scroll_direction_down", "wayland_scroll_direction_left",
    "wayland_scroll_direction_right", "wayland_scroll_direction_up",
]
