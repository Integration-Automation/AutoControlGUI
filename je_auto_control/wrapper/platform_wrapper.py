import sys

from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform in ["win32", "cygwin", "msys"]:
    from je_auto_control.wrapper._platform_windows import (  # noqa: F401  # reason: facade re-export
        keyboard, keyboard_check, keyboard_keys_table,
        mouse, mouse_keys_table, special_mouse_keys_table,
        screen, recorder,
    )
elif sys.platform == "darwin":
    from je_auto_control.wrapper._platform_osx import (  # noqa: F401  # reason: facade re-export
        keyboard, keyboard_check, keyboard_keys_table,
        mouse, mouse_keys_table, special_mouse_keys_table,
        screen, recorder,
    )
elif sys.platform in ["linux", "linux2"]:
    from je_auto_control.wrapper._platform_linux import (  # noqa: F401  # reason: facade re-export
        keyboard, keyboard_check, keyboard_keys_table,
        mouse, mouse_keys_table, special_mouse_keys_table,
        screen, recorder,
    )
else:
    raise AutoControlException("unknown operating system")

if None in [keyboard_keys_table, mouse_keys_table, keyboard, mouse, screen]:
    raise AutoControlException("Can't init auto control")


__all__ = [
    "keyboard", "keyboard_check", "keyboard_keys_table",
    "mouse", "mouse_keys_table", "special_mouse_keys_table",
    "screen", "recorder",
]
