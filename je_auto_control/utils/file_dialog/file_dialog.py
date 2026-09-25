"""Handle native file Open / Save-As / folder-picker dialogs.

A universal RPA pain: recorders don't capture the OS file dialog, so
everyone hand-rolls "type the full path + Enter". This waits for the
native dialog window, types the path into it, and confirms — in one call.

The window-wait / type / confirm steps go through an injectable
:class:`FileDialogDriver` so the orchestration is unit-tested without a
real dialog; the default driver uses the window + keyboard wrappers.
Imports no ``PySide6``.
"""
import time
from typing import Dict, Optional

_DEFAULT_TITLES = {"open": "Open", "save": "Save As", "folder": "Select Folder"}


class FileDialogDriver:
    """Pluggable window-wait / type / confirm steps for a file dialog."""

    def wait_window(self, title: str, timeout_s: float) -> bool:
        """Wait for a window titled exactly ``title`` and bring it to the front.

        A substring match took "How to reopen closed tabs - Google Chrome" for
        the Open dialog, and nothing was focused: the path and Enter went to
        whatever window was active. ``False`` (not handled) when no such
        window appears or it cannot be brought to the front.
        """
        from je_auto_control.wrapper.window_backends import get_backend
        backend = get_backend()
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        wanted = title.strip().casefold()
        while True:
            window_id = next((window for window, name in backend.list_windows()
                              if name.strip().casefold() == wanted), None)
            if window_id is not None:
                return backend.bring_to_front(window_id)
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.2)

    def type_path(self, path: str) -> None:
        from je_auto_control.wrapper.auto_control_keyboard import write
        write(str(path))

    def confirm(self, key: str) -> None:
        from je_auto_control.utils.cua_action.cua_action import resolve_key_name
        from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
        # The default "enter" is not a name the Windows key table knows
        # (it says "return"), so the default confirm step failed there.
        type_keyboard(resolve_key_name(str(key)))


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
