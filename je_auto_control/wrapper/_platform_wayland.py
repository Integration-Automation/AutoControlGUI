"""Wayland platform wrapper.

Mirrors the public surface of :mod:`je_auto_control.wrapper._platform_linux`
but routes keyboard / mouse / screen calls through the Wayland CLI
helpers (wtype, ydotool, grim) rather than X11's XTest extension.

The mouse-button table reuses the X11 button codes (left=1, right=3,
middle=2) — that's the public schema callers depend on. The internal
ydotool BTN_* hex codes are converted in :mod:`linux_wayland.mouse`
so the public mouse_keys_table stays consistent across platforms.
"""
from je_auto_control.linux_wayland import keyboard as wayland_keyboard
from je_auto_control.linux_wayland import listener as wayland_listener
from je_auto_control.linux_wayland import mouse as wayland_mouse
from je_auto_control.linux_wayland import record as wayland_record
from je_auto_control.linux_wayland import screen as wayland_screen
from je_auto_control.linux_wayland.keymap import (
    keyboard_keys_table as _wayland_keyboard_table,
)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


autocontrol_logger.info("Load Linux Wayland Setting")

keyboard_keys_table = dict(_wayland_keyboard_table)

mouse_keys_table = {
    "mouse_left": wayland_mouse.wayland_mouse_left,
    "mouse_middle": wayland_mouse.wayland_mouse_middle,
    "mouse_right": wayland_mouse.wayland_mouse_right,
}

special_mouse_keys_table = {
    "scroll_up": wayland_mouse.wayland_scroll_direction_up,
    "scroll_down": wayland_mouse.wayland_scroll_direction_down,
    "scroll_left": wayland_mouse.wayland_scroll_direction_left,
    "scroll_right": wayland_mouse.wayland_scroll_direction_right,
}

keyboard = wayland_keyboard
mouse = wayland_mouse
keyboard_check = wayland_listener
screen = wayland_screen
recorder = wayland_record.wayland_recorder


if None in [keyboard_keys_table, mouse_keys_table, special_mouse_keys_table,
            keyboard, mouse, screen, recorder]:
    raise AutoControlException("Can't init auto control (Wayland)")


__all__ = [
    "keyboard", "keyboard_check", "keyboard_keys_table",
    "mouse", "mouse_keys_table", "recorder",
    "screen", "special_mouse_keys_table",
]
