"""Platform-specific hotkey daemon backends (Strategy pattern)."""
import sys

from je_auto_control.utils.hotkey.backends.base import HotkeyBackend


def get_backend() -> HotkeyBackend:
    """Return the backend for the current platform."""
    if sys.platform.startswith("win"):
        from je_auto_control.utils.hotkey.backends.windows_backend import (
            WindowsHotkeyBackend,
        )
        return WindowsHotkeyBackend()
    if sys.platform == "darwin":
        from je_auto_control.utils.hotkey.backends.macos_backend import (
            MacOSHotkeyBackend,
        )
        return MacOSHotkeyBackend()
    if sys.platform.startswith("linux"):
        from je_auto_control.utils.hotkey.backends.linux_backend import (
            LinuxHotkeyBackend,
        )
        return LinuxHotkeyBackend()
    raise NotImplementedError(
        f"HotkeyDaemon has no backend for platform {sys.platform!r}"
    )


__all__ = ["HotkeyBackend", "get_backend"]
