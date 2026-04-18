"""Global hotkey daemon — binds OS-level hotkeys to action JSON files."""
from je_auto_control.utils.hotkey.hotkey_daemon import (
    HotkeyDaemon, HotkeyBinding, default_hotkey_daemon,
)

__all__ = ["HotkeyDaemon", "HotkeyBinding", "default_hotkey_daemon"]
