"""Wayland mouse backend via the ydotool CLI.

Wayland compositors do not let arbitrary clients move the cursor or
synthesise buttons; the ydotool daemon owns ``/dev/uinput`` and
arbitrates on our behalf. Buttons here are the BTN_* codes that
ydotool consumes (``0xC0`` left, ``0xC1`` right, ``0xC2`` middle —
ydotool's documented values for the ``click`` verb).
"""
from __future__ import annotations

import os
import subprocess  # nosec B404  # reason: argv-list, no shell interpolation
import time
from functools import lru_cache
from typing import Mapping, Optional, Tuple

from je_auto_control.linux_wayland._detect import WAYLAND_YDOTOOL, binary_path
from je_auto_control.linux_wayland._layout import layout_origin
from je_auto_control.linux_wayland._select_input import emitted
from je_auto_control.linux_wayland._ydotool_cli import reject_legacy_cli
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


# ydotool ``click`` accepts hex bitmasks: the low nibble selects the
# button (0 left, 1 right, 2 middle) and the high bits toggle the edge —
# ``0x40`` press-down, ``0x80`` release-up. The constants below carry both
# edges set (a full down+up click); ``_press_code`` / ``_release_code``
# isolate a single edge so a press+move+release drag actually holds.
_YDOTOOL_DOWN_BIT = 0x40
_YDOTOOL_UP_BIT = 0x80

wayland_mouse_left = 0xC0
wayland_mouse_middle = 0xC2
wayland_mouse_right = 0xC1
wayland_scroll_direction_up = 1
wayland_scroll_direction_down = -1
wayland_scroll_direction_left = -2
wayland_scroll_direction_right = 2

_INSTALL_HINT = (
    "ydotool 1.0 or newer is required for Wayland mouse input. "
    "Install it with your package manager (Arch: `pacman -S ydotool`; "
    "Fedora: `dnf install ydotool`; Debian: from unstable — trixie ships no "
    "package and bookworm's 0.1.8 is too old) and ensure ydotoold runs with "
    "/dev/uinput permission."
)


def _require_ydotool() -> str:
    path = binary_path(WAYLAND_YDOTOOL)
    if path is None:
        raise AutoControlException(_INSTALL_HINT)
    return reject_legacy_cli(path)


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


POINTER_ACCEL_ENV = "JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL"
POINTER_ACCEL_MODES = ("warn", "flat", "strict")

_ACCELERATION_ADVICE = (
    "Disable pointer acceleration for the ydotoold device (sway: `input "
    "type:pointer accel_profile flat` plus `pointer_accel 0`) or install "
    "liboeffis so the libei path can be used."
)

_ACCELERATION_WARNING = (
    "Wayland absolute move fell back to ydotool. `mousemove --absolute` is "
    "relative motion under the hood, so the compositor's pointer "
    "acceleration scales it: measured against a real wlroots session, "
    "libinput's default adaptive profile lands the cursor twice as far from "
    f"the corner as asked. {_ACCELERATION_ADVICE} With acceleration off, set "
    f"{POINTER_ACCEL_ENV}=flat to silence this; set it to strict to have the "
    "move refused instead of landing somewhere else."
)

_ACCELERATION_REFUSAL = (
    f"{POINTER_ACCEL_ENV}=strict, and this absolute move fell back to "
    "ydotool, whose `mousemove --absolute` is relative motion the compositor "
    f"scales — so the cursor would not land where asked. {_ACCELERATION_ADVICE} "
    f"Then set {POINTER_ACCEL_ENV}=flat, or unset it to warn and move anyway."
)


def pointer_accel_mode(environ: Optional[Mapping[str, str]] = None) -> str:
    """Return the operator's declared pointer-acceleration policy.

    The compositor's acceleration factor cannot be read back by the client,
    so this backend cannot compensate for it — only the operator knows
    whether it is switched off. This is how they say so:

    * ``warn`` — the default, and what an unset or unrecognised value means:
      log the caveat once per process and send the move regardless.
    * ``flat`` — acceleration is off for the ydotoold device, the move is
      pixel-accurate, and nothing needs saying.
    * ``strict`` — refuse to send an absolute move the compositor would
      scale, rather than let a click land silently in the wrong place.
    """
    env = environ if environ is not None else os.environ
    declared = (env.get(POINTER_ACCEL_ENV) or "").strip().lower()
    if not declared:
        return "warn"
    if declared in POINTER_ACCEL_MODES:
        return declared
    _warn_once(
        f"{POINTER_ACCEL_ENV}={declared} is not one of "
        f"{', '.join(POINTER_ACCEL_MODES)}; treating it as warn.",
    )
    return "warn"


def _apply_accel_policy() -> None:
    """Gate a ydotool absolute move on :func:`pointer_accel_mode`."""
    mode = pointer_accel_mode()
    if mode == "flat":
        return
    if mode == "strict":
        raise AutoControlException(_ACCELERATION_REFUSAL)
    _warn_about_acceleration()


def _ydotool_point(x: int, y: int) -> Tuple[int, int]:
    """Translate a layout coordinate into ydotool's absolute space.

    ``mousemove --absolute`` emits no absolute event. It sends ``INT32_MIN``
    on both axes to drive the cursor into the corner the compositor clamps
    to, then sends the target as a relative displacement — so its origin is
    the top-left of the *output layout*, not layout ``(0, 0)``. The two are
    the same point only while every output sits at a non-negative position;
    put a monitor left of the primary one and they differ by
    :func:`~je_auto_control.linux_wayland._layout.layout_origin`, which is
    exactly the correction the capture path already applies.

    Measured rather than reasoned: on a real wlroots session whose left-hand
    output sits at ``x=-1280`` (``docker/Dockerfile.seat``), with the
    pointer's acceleration disabled, ``--absolute -x 10 -y 10`` puts the
    cursor at layout ``(-1270, 10)``. Without this subtraction a caller
    asking for layout ``(-1270, 10)`` would land 1,280 pixels away, on the
    other monitor.
    """
    origin_x, origin_y = layout_origin()
    return x - origin_x, y - origin_y


def set_position(x: int, y: int) -> None:
    """Move the cursor to absolute (x, y). Uses libei when available.

    The libei path is absolute at the protocol level and lands exactly. The
    ydotool fallback cannot: see :func:`_ydotool_point` for the origin it
    counts from, and note that the compositor's pointer acceleration is
    applied to the relative motion it really sends, so the move is only
    pixel-accurate where that acceleration is switched off. ydotool's own
    ``--help`` says as much; by default this backend logs it once per
    process rather than letting a click land silently in the wrong place.
    :func:`pointer_accel_mode` documents the environment variable an
    operator sets to silence that (acceleration is off) or to have the move
    refused outright.

    :raises AutoControlException: on the ydotool path when the operator has
        set ``JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=strict``.
    """
    libei = _try_libei()
    if libei is not None and emitted(
            libei, lambda device: device.set_position(int(x), int(y))):
        return
    _apply_accel_policy()
    time.sleep(0.01)
    target_x, target_y = _ydotool_point(int(x), int(y))
    _run([_require_ydotool(), "mousemove", "--absolute",
          "-x", str(target_x), "-y", str(target_y)])


@lru_cache(maxsize=32)
def _warn_once(message: str) -> None:
    """Log ``message`` at warning level, once per process per distinct text.

    Cached rather than latched on a module global: these caveats are worth
    saying and not worth repeating on every move of a script that makes
    thousands. ``_warn_once.cache_clear()`` re-arms them. The bound is there
    because the key includes an operator-supplied env value; evicting only
    costs a repeated line.
    """
    autocontrol_logger.warning(message)


def _warn_about_acceleration() -> None:
    """Log the ydotool absolute-move caveat, once per process."""
    _warn_once(_ACCELERATION_WARNING)


def _try_libei():
    """Return a connected :class:`LibeiBackend`, or None when CLI should win."""
    try:
        from je_auto_control.linux_wayland._select_input import active_backend
        return active_backend()
    except (ImportError, RuntimeError, OSError):
        return None


# ydotool's ``click`` verb and libei speak different button numbers: the
# constants above are ydotool's bitmask nibbles, libei takes raw evdev
# BTN_* codes. Scroll needs a conversion of its own — see
# ``_LIBEI_VERTICAL_SIGN``.
_BTN_LEFT = 272
_BTN_RIGHT = 273
_BTN_MIDDLE = 274

_EVDEV_BUTTONS = {
    wayland_mouse_left: _BTN_LEFT,
    wayland_mouse_right: _BTN_RIGHT,
    wayland_mouse_middle: _BTN_MIDDLE,
}


def _evdev_button(mouse_keycode: int) -> Optional[int]:
    """Map this module's public button code onto an evdev BTN_* code.

    A press- or release-only code has one edge bit cleared; restoring both
    gives back the canonical constant the table is keyed on.
    """
    canonical = int(mouse_keycode) | _YDOTOOL_DOWN_BIT | _YDOTOOL_UP_BIT
    return _EVDEV_BUTTONS.get(canonical)


def _press_code(mouse_keycode: int) -> int:
    """Button-down only: set the down-bit, clear the up-bit."""
    return (int(mouse_keycode) | _YDOTOOL_DOWN_BIT) & ~_YDOTOOL_UP_BIT


def _release_code(mouse_keycode: int) -> int:
    """Button-up only: set the up-bit, clear the down-bit."""
    return (int(mouse_keycode) | _YDOTOOL_UP_BIT) & ~_YDOTOOL_DOWN_BIT


def press_mouse(mouse_keycode: int) -> None:
    """Press a mouse button and hold it (down edge only)."""
    if _emit_button(mouse_keycode, press=True):
        return
    time.sleep(0.01)
    _run([_require_ydotool(), "click", f"{_press_code(mouse_keycode):#x}"])


def release_mouse(mouse_keycode: int) -> None:
    """Release a held mouse button (up edge only)."""
    if _emit_button(mouse_keycode, press=False):
        return
    time.sleep(0.01)
    _run([_require_ydotool(), "click", f"{_release_code(mouse_keycode):#x}"])


def _emit_button(mouse_keycode: int, *, press: bool) -> bool:
    """Send one button edge through libei; False means fall back to the CLI."""
    button = _evdev_button(mouse_keycode)
    if button is None:
        return False
    libei = _try_libei()
    if libei is None:
        return False
    if press:
        return emitted(libei, lambda device: device.press_button(button))
    return emitted(libei, lambda device: device.release_button(button))


def click_mouse(mouse_keycode: int, x: Optional[int] = None,
                y: Optional[int] = None) -> None:
    """Press + release a mouse button, optionally moving first."""
    if x is not None and y is not None:
        set_position(int(x), int(y))
    if _emit_button(mouse_keycode, press=True):
        # Not _emit_button: a refused release has to reach the CLI, or the
        # button stays down for the rest of the session.
        release_mouse(mouse_keycode)
        return
    time.sleep(0.01)
    _run([_require_ydotool(), "click", f"{int(mouse_keycode):#x}"])


#: Sign applied to the vertical axis on the way to libei.
#:
#: The two sides count wheels in opposite directions. This module's
#: ``wayland_scroll_direction_*`` constants are in the kernel's ``REL_WHEEL``
#: frame, because that is what ydotool writes into ``/dev/uinput``: positive
#: is up. libei is in the ``wl_pointer`` / libinput frame, where positive is
#: down — libinput's own evdev reader negates ``REL_WHEEL`` to get there, and
#: the other libei sender that documents its sign (enigo) passes a
#: "positive scrolls down" value straight through to ``scroll_discrete``.
#:
#: Horizontal needs no flip: ``REL_HWHEEL`` and libinput both count right as
#: positive, and libinput passes that axis through unnegated.
#:
#: What ``docker/eis_verify.py`` measured is the half either frame agrees on:
#: ``scroll(0, 1)`` reaches a real EIS server as ``(0, 120)`` — one whole
#: click, on the y axis, sign preserved end to end, no axis swap. The frame
#: the compositor reads that in is the half above.
_LIBEI_VERTICAL_SIGN = -1


def _wheel_deltas(scroll_value: int, scroll_direction: int) -> Tuple[int, int]:
    """Split ``(value, direction)`` into the ``(x, y)`` detents to send.

    ``scroll_direction`` carries axis and sign, per this module's
    ``wayland_scroll_direction_*`` constants: +-1 vertical, +-2 horizontal.
    """
    direction = int(scroll_direction)
    amount = abs(int(scroll_value)) * (1 if direction > 0 else -1)
    return (0, amount) if abs(direction) == 1 else (amount, 0)


def scroll(scroll_value: int,
           scroll_direction: int = wayland_scroll_direction_down) -> None:
    """Scroll ``scroll_value`` notches in ``scroll_direction``.

    The signature mirrors the x11 backend's ``scroll(scroll_value,
    scroll_direction)`` because the wrapper treats every Linux backend
    uniformly — it cannot tell Wayland from X11 by ``sys.platform``. The
    previous ``(direction, x, y)`` shape silently bound the wrapper's
    direction to ``x`` and then dropped it, so every scroll went the same way.

    Prefers libei, which delivers whole wheel clicks without a uinput daemon;
    the vertical axis is negated on the way out (``_LIBEI_VERTICAL_SIGN``).

    On the ydotool fallback both axes are always passed, as ydotool's own
    documented example does (``ydotool mousemove -w -x 0 -y -1``) — leaving
    one out would rely on it defaulting to zero, which the tool does not
    promise. Positive is up / right there, matching the kernel's
    ``REL_WHEEL`` convention that ydotool writes.
    """
    delta_x, delta_y = _wheel_deltas(scroll_value, scroll_direction)
    libei = _try_libei()
    if libei is not None and emitted(libei, lambda device: device.scroll(
            delta_x, _LIBEI_VERTICAL_SIGN * delta_y)):
        return
    _run([_require_ydotool(), "mousemove", "--wheel",
          "-x", str(delta_x), "-y", str(delta_y)])


def send_mouse_event_to_window(*_args, **_kwargs) -> None:
    """Wayland has no per-window mouse injection."""
    raise NotImplementedError(
        "Wayland forbids per-window mouse injection (no XSendEvent "
        "equivalent). Focus the window first, then call click_mouse, "
        "or use the X11 backend.",
    )


__all__ = [
    "POINTER_ACCEL_ENV", "POINTER_ACCEL_MODES", "click_mouse",
    "pointer_accel_mode", "position", "press_mouse", "release_mouse",
    "scroll", "send_mouse_event_to_window", "set_position",
    "wayland_mouse_left", "wayland_mouse_middle", "wayland_mouse_right",
    "wayland_scroll_direction_down", "wayland_scroll_direction_left",
    "wayland_scroll_direction_right", "wayland_scroll_direction_up",
]
