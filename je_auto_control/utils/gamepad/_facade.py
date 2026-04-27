"""Friendly gamepad facade backed by the optional ``vgamepad`` package.

Why this exists separately from the ``windows/`` backend tree: ViGEm
isn't a keyboard / mouse driver — it's a virtual HID gamepad bus. The
wrapper layer that picks SendInput vs Interception is keyboard / mouse
specific; gamepad input is its own surface (axes, triggers, dpad,
buttons) that no other AutoControl module emits, so it lives under
``utils/`` alongside the other peripheral helpers.

Lazy imports keep ``import je_auto_control`` cheap on machines without
``vgamepad`` installed: nothing in this module reaches for the
optional dep until the operator actually instantiates a gamepad.
"""
from __future__ import annotations

import threading
from typing import Dict, Optional, Tuple


class GamepadUnavailable(RuntimeError):
    """Raised when ``vgamepad`` or ViGEmBus is missing."""


# Friendly names → vgamepad button enum lookup keys. Kept as plain
# strings so the executor / MCP / JSON action files can use them
# without taking a dep on the ``vgamepad`` import.
GAMEPAD_BUTTONS: Tuple[str, ...] = (
    "a", "b", "x", "y",
    "lb", "rb",
    "back", "start", "guide",
    "ls", "rs",  # left/right stick presses
)

DPAD_DIRECTIONS: Tuple[str, ...] = (
    "up", "down", "left", "right",
    "up_left", "up_right", "down_left", "down_right", "none",
)

_BUTTON_ATTR_MAP: Dict[str, str] = {
    "a": "XUSB_GAMEPAD_A",
    "b": "XUSB_GAMEPAD_B",
    "x": "XUSB_GAMEPAD_X",
    "y": "XUSB_GAMEPAD_Y",
    "lb": "XUSB_GAMEPAD_LEFT_SHOULDER",
    "rb": "XUSB_GAMEPAD_RIGHT_SHOULDER",
    "back": "XUSB_GAMEPAD_BACK",
    "start": "XUSB_GAMEPAD_START",
    "guide": "XUSB_GAMEPAD_GUIDE",
    "ls": "XUSB_GAMEPAD_LEFT_THUMB",
    "rs": "XUSB_GAMEPAD_RIGHT_THUMB",
}

_DPAD_ATTR_MAP: Dict[str, str] = {
    "up": "XUSB_GAMEPAD_DPAD_UP",
    "down": "XUSB_GAMEPAD_DPAD_DOWN",
    "left": "XUSB_GAMEPAD_DPAD_LEFT",
    "right": "XUSB_GAMEPAD_DPAD_RIGHT",
    "up_left": "XUSB_GAMEPAD_DPAD_UP_LEFT",
    "up_right": "XUSB_GAMEPAD_DPAD_UP_RIGHT",
    "down_left": "XUSB_GAMEPAD_DPAD_DOWN_LEFT",
    "down_right": "XUSB_GAMEPAD_DPAD_DOWN_RIGHT",
    "none": "XUSB_GAMEPAD_DPAD_NONE",
}


def _import_vgamepad():
    """Resolve ``vgamepad`` lazily so the optional dep is opt-in."""
    try:
        import vgamepad  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dep
        raise GamepadUnavailable(
            "vgamepad is not installed. Run "
            "`pip install vgamepad` after installing the ViGEmBus "
            "driver from https://github.com/nefarius/ViGEmBus."
        ) from exc
    return vgamepad


def is_available() -> bool:
    """Return True if both ``vgamepad`` and ViGEmBus are reachable."""
    try:
        vg = _import_vgamepad()
    except GamepadUnavailable:
        return False
    # Instantiating the gamepad is the only reliable check for the bus
    # driver. Tear down right after so we don't leak a connection.
    try:
        pad = vg.VX360Gamepad()
    except (OSError, RuntimeError):
        return False
    try:
        pad.reset()
    except (OSError, RuntimeError):
        pass
    return True


def _clamp_signed_short(value) -> int:
    """Clamp ``value`` to the int16 range vgamepad's left/right sticks expect."""
    n = int(value)
    if n > 32767:
        return 32767
    if n < -32768:
        return -32768
    return n


def _clamp_byte(value) -> int:
    """Clamp ``value`` to the 0..255 trigger range."""
    n = int(value)
    if n > 255:
        return 255
    if n < 0:
        return 0
    return n


class VirtualGamepad:
    """Wrap ``vgamepad.VX360Gamepad`` with friendly string-keyed methods.

    Use as a context manager when possible so the underlying ViGEm
    handle is freed cleanly::

        from je_auto_control.utils.gamepad import VirtualGamepad
        with VirtualGamepad() as pad:
            pad.press_button("a")
            pad.release_button("a")
            pad.set_left_stick(16000, 0)
            pad.update()  # auto-called when leaving the context
    """

    def __init__(self) -> None:
        vg = _import_vgamepad()
        try:
            self._pad = vg.VX360Gamepad()
        except (OSError, RuntimeError) as exc:
            raise GamepadUnavailable(
                "ViGEmBus driver is not installed or the service is "
                "stopped. Install from "
                "https://github.com/nefarius/ViGEmBus and reboot."
            ) from exc
        self._vg = vg
        self._closed = False

    # --- buttons -------------------------------------------------------------

    def _resolve_button(self, name: str):
        try:
            attr = _BUTTON_ATTR_MAP[name.lower()]
        except KeyError as exc:
            raise ValueError(
                f"unknown gamepad button {name!r}; choose from "
                f"{GAMEPAD_BUTTONS!r}"
            ) from exc
        return getattr(self._vg.XUSB_BUTTON, attr)

    def press_button(self, name: str, *, update: bool = True) -> None:
        """Press a face / shoulder / stick button (and optionally flush)."""
        self._pad.press_button(button=self._resolve_button(name))
        if update:
            self._pad.update()

    def release_button(self, name: str, *, update: bool = True) -> None:
        self._pad.release_button(button=self._resolve_button(name))
        if update:
            self._pad.update()

    def click_button(self, name: str) -> None:
        """Press then release in one shot."""
        self.press_button(name, update=False)
        self.release_button(name, update=True)

    # --- dpad ---------------------------------------------------------------

    def set_dpad(self, direction: str, *, update: bool = True) -> None:
        """Hold a dpad direction (use ``"none"`` to release)."""
        try:
            attr = _DPAD_ATTR_MAP[direction.lower()]
        except KeyError as exc:
            raise ValueError(
                f"unknown dpad direction {direction!r}; choose from "
                f"{DPAD_DIRECTIONS!r}"
            ) from exc
        self._pad.directional_pad(direction=getattr(self._vg.XUSB_BUTTON, attr))
        if update:
            self._pad.update()

    # --- sticks / triggers --------------------------------------------------

    def set_left_stick(self, x: int, y: int, *, update: bool = True) -> None:
        """Move the left analogue stick. ``x``/``y`` clamp to int16."""
        self._pad.left_joystick(
            x_value=_clamp_signed_short(x),
            y_value=_clamp_signed_short(y),
        )
        if update:
            self._pad.update()

    def set_right_stick(self, x: int, y: int, *, update: bool = True) -> None:
        """Move the right analogue stick. ``x``/``y`` clamp to int16."""
        self._pad.right_joystick(
            x_value=_clamp_signed_short(x),
            y_value=_clamp_signed_short(y),
        )
        if update:
            self._pad.update()

    def set_left_trigger(self, value: int, *, update: bool = True) -> None:
        """0–255 left-trigger pressure."""
        self._pad.left_trigger(value=_clamp_byte(value))
        if update:
            self._pad.update()

    def set_right_trigger(self, value: int, *, update: bool = True) -> None:
        """0–255 right-trigger pressure."""
        self._pad.right_trigger(value=_clamp_byte(value))
        if update:
            self._pad.update()

    # --- batch / lifecycle --------------------------------------------------

    def update(self) -> None:
        """Flush queued state changes to the driver in one packet."""
        self._pad.update()

    def reset(self) -> None:
        """Clear every pressed button / stick offset / trigger pressure."""
        self._pad.reset()
        self._pad.update()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._pad.reset()
            self._pad.update()
        except (OSError, RuntimeError):
            pass
        self._closed = True

    # --- context manager ----------------------------------------------------

    def __enter__(self) -> "VirtualGamepad":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


# Process-wide singleton -----------------------------------------------------

_default_pad: Optional[VirtualGamepad] = None
_default_lock = threading.Lock()


def default_gamepad() -> VirtualGamepad:
    """Lazily-created process-wide :class:`VirtualGamepad` instance."""
    global _default_pad
    with _default_lock:
        if _default_pad is None or _default_pad._closed:  # noqa: SLF001
            _default_pad = VirtualGamepad()
        return _default_pad


def reset_default_gamepad() -> None:
    """Tear down the singleton — used by tests / shutdown hooks."""
    global _default_pad
    with _default_lock:
        if _default_pad is not None:
            _default_pad.close()
            _default_pad = None


__all__ = [
    "DPAD_DIRECTIONS", "GAMEPAD_BUTTONS",
    "GamepadUnavailable", "VirtualGamepad",
    "default_gamepad", "is_available", "reset_default_gamepad",
]
