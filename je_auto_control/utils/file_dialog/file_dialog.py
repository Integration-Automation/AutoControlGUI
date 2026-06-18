"""Handle native file Open / Save-As / folder-picker dialogs.

A universal RPA pain: recorders don't capture the OS file dialog, so
everyone hand-rolls "type the full path + Enter". This waits for the
native dialog window, types the path into it, and confirms — in one call.

The window-wait / type / confirm steps go through an injectable
:class:`FileDialogDriver` so the orchestration is unit-tested without a
real dialog; the default driver uses the window + keyboard wrappers.
Imports no ``PySide6``.
"""
from typing import Dict, Optional

_DEFAULT_TITLES = {"open": "Open", "save": "Save As", "folder": "Select Folder"}


class FileDialogDriver:
    """Pluggable window-wait / type / confirm steps for a file dialog."""

    def wait_window(self, title: str, timeout_s: float) -> bool:
        from je_auto_control.wrapper.auto_control_window import wait_for_window
        try:
            wait_for_window(title, timeout=float(timeout_s))
            return True
        except (OSError, RuntimeError, ValueError):
            return False

    def type_path(self, path: str) -> None:
        from je_auto_control.wrapper.auto_control_keyboard import write
        write(str(path))

    def confirm(self, key: str) -> None:
        from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
        type_keyboard(str(key))


def handle_file_dialog(path: str, *, action: str = "open",
                       window_title: Optional[str] = None,
                       timeout_s: float = 10.0, confirm_key: str = "enter",
                       driver: Optional[FileDialogDriver] = None,
                       ) -> Dict[str, object]:
    """Wait for a native file dialog, type ``path``, and confirm.

    :param action: ``open`` / ``save`` / ``folder`` — picks a default
        dialog title when ``window_title`` is not given.
    :returns: ``{"handled": bool, "title": str}``.
    """
    title = window_title or _DEFAULT_TITLES.get(action, _DEFAULT_TITLES["open"])
    drv = driver or FileDialogDriver()
    if not drv.wait_window(title, float(timeout_s)):
        return {"handled": False, "title": title}
    drv.type_path(str(path))
    drv.confirm(str(confirm_key))
    return {"handled": True, "title": title}
