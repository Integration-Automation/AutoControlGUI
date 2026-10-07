"""Read native mouse button state before GUI raw holds, without capturing screen pixels."""
import sys
from typing import Hashable

from je_auto_control.utils.platform_id import is_windows, is_x11_unix


def _button_state(keycode: Hashable) -> bool | None:
    if is_windows():
        # pylint: disable=import-outside-toplevel  # reason: lazy native platform dependency
        from je_auto_control.windows.core.utils.win32_ctype_input import user32
        # pylint: enable=import-outside-toplevel
        # pylint: disable=import-outside-toplevel  # reason: lazy native platform dependency
        from je_auto_control.wrapper.platform_wrapper import mouse_keys_table
        # pylint: enable=import-outside-toplevel
        name = next((name for name, value in mouse_keys_table.items() if value == keycode), '')
        virtual_key = {'mouse_left': 1, 'mouse_right': 2, 'mouse_middle': 4}.get(name)
        return bool(user32.GetAsyncKeyState(virtual_key) & 0x8000) if virtual_key is not None else None
    if sys.platform == 'darwin':
        import Quartz  # pylint: disable=import-outside-toplevel,import-error  # reason: lazy native platform dependency
        return bool(Quartz.CGEventSourceButtonState(0, keycode)) if keycode in (0, 1, 2) else None
    if is_x11_unix():
        # pylint: disable=import-outside-toplevel  # reason: lazy native platform dependency
        from je_auto_control.linux_with_x11.core.utils.x11_linux_display import display
        # pylint: enable=import-outside-toplevel
        mask = {1: 1 << 8, 2: 1 << 9, 3: 1 << 10}.get(keycode) if isinstance(keycode, int) else None
        return bool(display.screen().root.query_pointer().mask & mask) if mask is not None else None
    return None
