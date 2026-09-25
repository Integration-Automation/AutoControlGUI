"""MCP adapters for mouse, keyboard and virtual gamepad (ViGEm) input.

Same contract as :mod:`._handlers` -- normalise arguments and return values so
they survive the JSON-RPC boundary, with every project import lazy -- split out
by theme because ``_handlers.py`` is over the 750-line limit.
"""
from typing import Any, Dict, List, Optional


# === Mouse / keyboard =======================================================

def click_mouse(mouse_keycode: str = "mouse_left",
                x: Optional[int] = None,
                y: Optional[int] = None) -> List[Any]:
    from je_auto_control.wrapper.auto_control_mouse import click_mouse as _click
    keycode, click_x, click_y = _click(mouse_keycode, x, y)
    # Real wrapper resolves the string keycode to an int via the keys table;
    # the fake backend keeps it as a string. Pass through whatever we got.
    resolved = int(keycode) if isinstance(keycode, int) else keycode
    return [resolved, int(click_x), int(click_y)]


def set_mouse_position(x: int, y: int) -> List[int]:
    from je_auto_control.wrapper.auto_control_mouse import set_mouse_position as _move
    moved = _move(int(x), int(y))
    return [int(moved[0]), int(moved[1])]


def get_mouse_position() -> List[int]:
    from je_auto_control.wrapper.auto_control_mouse import get_mouse_position as _pos
    pos = _pos()
    return [] if pos is None else [int(pos[0]), int(pos[1])]


def mouse_scroll(scroll_value: int,
                 x: Optional[int] = None,
                 y: Optional[int] = None,
                 scroll_direction: str = "scroll_down") -> List[Any]:
    from je_auto_control.wrapper.auto_control_mouse import mouse_scroll as _scroll
    value, direction = _scroll(int(scroll_value), x, y, scroll_direction)
    return [int(value), str(direction)]


def type_text(text: str) -> str:
    from je_auto_control.wrapper.auto_control_keyboard import write
    return write(text) or ""


def press_key(keycode: str) -> str:
    from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
    return type_keyboard(keycode) or ""


def hotkey(keys: List[str]) -> List[str]:
    from je_auto_control.wrapper.auto_control_keyboard import hotkey as _hotkey
    pressed, released = _hotkey(list(keys))
    return [pressed, released]


def drag(start_x: int, start_y: int, end_x: int, end_y: int,
         mouse_keycode: str = "mouse_left") -> List[int]:
    """Drag the cursor from (start_x, start_y) to (end_x, end_y)."""
    from je_auto_control.wrapper.auto_control_mouse import (
        press_mouse, release_mouse, set_mouse_position as _move,
    )
    _move(int(start_x), int(start_y))
    press_mouse(mouse_keycode, int(start_x), int(start_y))
    try:
        _move(int(end_x), int(end_y))
    except BaseException:
        # An end point the move refuses (off screen) left the button held
        # down; it is released where it was pressed.
        release_mouse(mouse_keycode, int(start_x), int(start_y))
        raise
    release_mouse(mouse_keycode, int(end_x), int(end_y))
    return [int(end_x), int(end_y)]


def send_key_to_window(window_title: str, keycode: str) -> str:
    from je_auto_control.wrapper.auto_control_keyboard import (
        send_key_event_to_window,
    )
    send_key_event_to_window(window_title, keycode)
    return "ok"


def send_mouse_to_window(window_title: str,
                         mouse_keycode: str = "mouse_left",
                         x: Optional[int] = None,
                         y: Optional[int] = None) -> str:
    from je_auto_control.windows.window import windows_window_manage as wm
    from je_auto_control.wrapper.auto_control_mouse import (
        send_mouse_event_to_window,
    )
    hit = next(((hwnd, title) for hwnd, title in wm.get_all_window_hwnd()
                if window_title.lower() in title.lower()), None)
    if hit is None:
        raise ValueError(f"no window matching {window_title!r}")
    send_mouse_event_to_window(hit[0], mouse_keycode, x=x, y=y)
    return "ok"


# === Virtual gamepad (ViGEm) ================================================

def gamepad_press(button: str) -> Dict[str, Any]:
    """Press a virtual Xbox 360 button by friendly name."""
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().press_button(button)
    return {"button": button, "state": "down"}


def gamepad_release(button: str) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().release_button(button)
    return {"button": button, "state": "up"}


def gamepad_click(button: str) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().click_button(button)
    return {"button": button, "state": "click"}


def gamepad_dpad(direction: str) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_dpad(direction)
    return {"dpad": direction}


def gamepad_left_stick(x: int, y: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_left_stick(int(x), int(y))
    return {"left_stick": [int(x), int(y)]}


def gamepad_right_stick(x: int, y: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_right_stick(int(x), int(y))
    return {"right_stick": [int(x), int(y)]}


def gamepad_left_trigger(value: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_left_trigger(int(value))
    return {"left_trigger": int(value)}


def gamepad_right_trigger(value: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_right_trigger(int(value))
    return {"right_trigger": int(value)}


def gamepad_reset() -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().reset()
    return {"reset": True}


# --- USB passthrough — delegate to the shared command module -------------


def usb_passthrough_enable(enabled: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.passthrough_enable(enabled)


def usb_passthrough_status() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.passthrough_status()


def usb_acl_list() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_list()


def usb_acl_add(vendor_id: str, product_id: str,
                serial: Optional[str] = None, allow: bool = True,
                prompt_on_open: bool = False, label: str = "") -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_add(
        vendor_id, product_id, serial=serial, allow=allow,
        prompt_on_open=prompt_on_open, label=label,
    )


def usb_acl_remove(vendor_id: str, product_id: str,
                   serial: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_remove(vendor_id, product_id, serial=serial)


def usb_acl_set_default(policy: str) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_set_default(policy)


def usb_loopback_list() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.loopback_list()


def usb_loopback_open(vendor_id: str, product_id: str,
                      serial: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.loopback_open(vendor_id, product_id, serial=serial)


def usb_remote_list() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.remote_list()


def usb_remote_open(vendor_id: str, product_id: str,
                    serial: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.remote_open(vendor_id, product_id, serial=serial)
