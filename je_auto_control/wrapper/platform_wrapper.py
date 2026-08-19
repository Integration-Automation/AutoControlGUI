import sys

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.platform_id import is_bsd, is_macos, is_windows

if is_windows():
    from je_auto_control.wrapper._platform_windows import (  # noqa: F401  # reason: facade re-export
        keyboard, keyboard_check, keyboard_keys_table,
        mouse, mouse_keys_table, special_mouse_keys_table,
        screen, recorder,
    )
elif is_macos():
    from je_auto_control.wrapper._platform_osx import (  # noqa: F401  # reason: facade re-export
        keyboard, keyboard_check, keyboard_keys_table,
        mouse, mouse_keys_table, special_mouse_keys_table,
        screen, recorder,
    )
elif sys.platform.startswith("linux"):
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
elif is_bsd():
    # A FreeBSD, OpenBSD or NetBSD desktop is an ordinary X11 desktop: the
    # same X server, the same python-Xlib, the same backend. There is no
    # Wayland branch here because the Wayland backend's fast path is libei,
    # whose socket and portal are Linux desktop infrastructure; a BSD running
    # Wayland reaches this through XWayland like any other X11 client.
    from je_auto_control.wrapper._platform_linux import (  # noqa: F401  # reason: facade re-export
        keyboard, keyboard_check, keyboard_keys_table,
        mouse, mouse_keys_table, special_mouse_keys_table,
        screen, recorder,
    )
else:
    raise AutoControlException(
        f"unknown operating system: {sys.platform!r}. Windows, macOS, Linux "
        f"and the BSDs are supported.")

if None in [keyboard_keys_table, mouse_keys_table, keyboard, mouse, screen]:
    raise AutoControlException("Can't init auto control")


__all__ = [
    "keyboard", "keyboard_check", "keyboard_keys_table",
    "mouse", "mouse_keys_table", "special_mouse_keys_table",
    "screen", "recorder",
]
