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
    from je_auto_control.linux_wayland import select_display_server
    from je_auto_control.utils.logging.logging_instance import (
        autocontrol_logger,
    )
    _DISPLAY_SERVER = select_display_server()
    if _DISPLAY_SERVER == "wayland":
        try:
            from je_auto_control.wrapper._platform_wayland import (  # noqa: F401  # reason: facade re-export
                keyboard, keyboard_check, keyboard_keys_table,
                mouse, mouse_keys_table, special_mouse_keys_table,
                screen, recorder,
            )
        except (ImportError, AutoControlException) as _wayland_error:
            autocontrol_logger.warning(
                "Wayland backend unavailable (%r); falling back to "
                "XWayland via the X11 backend. Set "
                "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11 to silence "
                "this warning.", _wayland_error,
            )
            from je_auto_control.wrapper._platform_linux import (  # noqa: F401  # reason: facade re-export
                keyboard, keyboard_check, keyboard_keys_table,
                mouse, mouse_keys_table, special_mouse_keys_table,
                screen, recorder,
            )
    else:
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
