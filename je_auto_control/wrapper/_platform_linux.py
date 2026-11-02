"""Assemble X11 services without acquiring displays or input devices."""
from typing import Dict, Tuple

from threading import Lock

from je_auto_control.linux_with_x11.core.utils.x11_linux_vk import get_keyboard_keys_table
from je_auto_control.linux_with_x11.keyboard import x11_linux_keyboard_control
from je_auto_control.linux_with_x11.listener import x11_linux_listener
from je_auto_control.linux_with_x11.mouse import x11_linux_mouse_control
from je_auto_control.linux_with_x11.mouse.x11_linux_mouse_control import (
    x11_linux_mouse_left, x11_linux_mouse_middle, x11_linux_mouse_right,
    x11_linux_scroll_direction_up, x11_linux_scroll_direction_down,
    x11_linux_scroll_direction_left, x11_linux_scroll_direction_right,
)
from je_auto_control.linux_with_x11.record.x11_linux_record import x11_linux_recorder
from je_auto_control.linux_with_x11.screen import x11_linux_screen
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper.backend_contract import (
    KeyboardCheckBackend, RecorderBackend, ScreenBackend,
    X11UnixKeyboardBackend, X11UnixMouseBackend,
)

mouse_keys_table = {
    "mouse_left": x11_linux_mouse_left,
    "mouse_middle": x11_linux_mouse_middle,
    "mouse_right": x11_linux_mouse_right,
}

special_mouse_keys_table = {
    "scroll_up": x11_linux_scroll_direction_up,
    "scroll_down": x11_linux_scroll_direction_down,
    "scroll_left": x11_linux_scroll_direction_left,
    "scroll_right": x11_linux_scroll_direction_right,
}

def _select_input_backend() -> Tuple[X11UnixKeyboardBackend,
                                     X11UnixMouseBackend]:
    """Pick keyboard/mouse modules based on JE_AUTOCONTROL_LINUX_BACKEND.

    Both candidates are checked against the seam's Unix protocols here, so a
    uinput backend that drifted from XTest's shape fails in this function
    rather than at a call site three layers up.

    Default is ``x11`` (the existing XTest backend). Set the env var
    to ``uinput`` to route synthetic input through ``/dev/uinput`` —
    required for games that read evdev and ignore XTest. Falls back
    to XTest with a warning when ``/dev/uinput`` isn't writable, so
    deployments can roll permissions out lazily.
    """
    import os

    from je_auto_control.utils.logging.logging_instance import (
        autocontrol_logger,
    )
    backend = os.environ.get(
        "JE_AUTOCONTROL_LINUX_BACKEND", "x11",
    ).strip().lower()
    if backend != "uinput":
        return x11_linux_keyboard_control, x11_linux_mouse_control
    try:
        from je_auto_control.linux_with_x11.uinput import (
            keyboard as uinput_keyboard,
            mouse as uinput_mouse,
            is_available,
        )
    except ImportError as error:
        autocontrol_logger.warning(
            "uinput backend requested but module import failed: "
            "%r — falling back to XTest.", error,
        )
        return x11_linux_keyboard_control, x11_linux_mouse_control
    if not is_available():
        autocontrol_logger.warning(
            "uinput backend requested but /dev/uinput is not writable "
            "— falling back to XTest. Run "
            "`sudo modprobe uinput && sudo chmod 666 /dev/uinput` "
            "or install the udev rule documented in new_features.",
        )
        return x11_linux_keyboard_control, x11_linux_mouse_control
    autocontrol_logger.info("Linux input backend: uinput (kernel)")
    return uinput_keyboard, uinput_mouse


_INPUT_PAIR: Tuple[X11UnixKeyboardBackend, X11UnixMouseBackend] | None = None
_input_lock = Lock()


def _get_input_backend() -> Tuple[X11UnixKeyboardBackend, X11UnixMouseBackend]:
    global _INPUT_PAIR  # pylint: disable=global-statement  # reason: one module owns this lazy cache
    with _input_lock:
        if _INPUT_PAIR is None:
            _INPUT_PAIR = _select_input_backend()
        return _INPUT_PAIR


class _Keyboard:

    """Select the shared input pair on the first keyboard operation."""
    def press_key(self, keycode: int) -> None:
        """Press a key through the selected input backend."""
        x11_linux_keyboard_control.validate_keycode(keycode)
        _get_input_backend()[0].press_key(keycode)

    def release_key(self, keycode: int) -> None:
        """Release a key through the selected input backend."""
        x11_linux_keyboard_control.validate_keycode(keycode)
        _get_input_backend()[0].release_key(keycode)


class _Mouse:

    """Select the shared input pair on the first pointer operation."""
    def position(self) -> Tuple[int, int]:
        """Read the pointer position through the selected input backend."""
        return _get_input_backend()[1].position()

    def set_position(self, x: int, y: int) -> None:
        """Move the pointer through the selected input backend."""
        _get_input_backend()[1].set_position(x, y)

    def press_mouse(self, mouse_keycode: int) -> None:
        """Press a button through the selected input backend."""
        _get_input_backend()[1].press_mouse(mouse_keycode)

    def release_mouse(self, mouse_keycode: int) -> None:
        """Release a button through the selected input backend."""
        _get_input_backend()[1].release_mouse(mouse_keycode)

    def click_mouse(self, mouse_keycode: int, x: int | None = None, y: int | None = None) -> None:
        """Click through the selected input backend."""
        _get_input_backend()[1].click_mouse(mouse_keycode, x, y)

    def scroll(self, scroll_value: int, scroll_direction: int) -> None:
        """Scroll through the selected input backend."""
        _get_input_backend()[1].scroll(scroll_value, scroll_direction)


keyboard: X11UnixKeyboardBackend = _Keyboard()
mouse: X11UnixMouseBackend = _Mouse()
keyboard_check: KeyboardCheckBackend = x11_linux_listener
screen: ScreenBackend = x11_linux_screen
recorder: RecorderBackend = x11_linux_recorder

#: Aliases of canonical key names; none on this backend (see ``_platform_windows``).
keyboard_key_aliases: Dict[str, str] = {}

if None in [mouse_keys_table, special_mouse_keys_table, keyboard, mouse, screen, recorder]:
    raise AutoControlException("Can't init auto control")


def __getattr__(name: str) -> dict[str, int]:
    """Keep explicit access to the public key table compatible."""
    if name == "keyboard_keys_table":
        return get_keyboard_keys_table()
    raise AttributeError(name)
