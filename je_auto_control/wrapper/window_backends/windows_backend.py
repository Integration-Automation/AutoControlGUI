"""Windows window-management backend, over the existing Win32 module."""
import sys
from typing import List, Optional, Tuple

from je_auto_control.wrapper.window_backends.base import WindowManageBackend


class WindowsWindowBackend(WindowManageBackend):
    """Delegates to :mod:`je_auto_control.windows.window.windows_window_manage`.

    That module is unchanged and stays the single home of the Win32 calls;
    this only adapts it to the shape the other platforms also answer in.
    """

    name = "win32"

    def __init__(self) -> None:
        self.available = sys.platform in ("win32", "cygwin", "msys")

    @property
    def _wm(self):
        """The Win32 module, imported lazily so other platforms never load it."""
        from je_auto_control.windows.window import windows_window_manage

        return windows_window_manage

    def list_windows(self) -> List[Tuple[int, str]]:
        return self._wm.get_all_window_hwnd()

    def foreground_window(self) -> int:
        return self._wm.get_foreground_window()

    def window_rect(self, window_id: int,
                    ) -> Optional[Tuple[int, int, int, int]]:
        return self._wm.get_window_rect(window_id)

    def window_process_id(self, window_id: int) -> int:
        return self._wm.get_window_process_id(window_id)

    def is_minimized(self, window_id: int) -> bool:
        return self._wm.is_window_minimized(window_id)

    def set_foreground(self, window_id: int) -> None:
        self._wm.set_foreground_window(window_id)

    def restore(self, window_id: int) -> None:
        self._wm.show_window(window_id, self._wm.SW_RESTORE)

    def show(self, window_id: int, cmd_show: int) -> None:
        self._wm.show_window(window_id, int(cmd_show))

    def close(self, window_id: int) -> bool:
        return self._wm.close_window(window_id)

    def minimize(self, window_id: int) -> bool:
        return self._wm.minimize_window(window_id)

    def move(self, window_id: int, x: int, y: int,
             width: int, height: int) -> bool:
        return self._wm.move_window(window_id, x, y, width, height)

    def post_key(self, window_id: int, keycode: int,
                 character: str = "") -> bool:
        return self._wm.post_key(window_id, keycode, character)

    def post_click(self, window_id: int, button: str, x: int, y: int) -> bool:
        return self._wm.post_click(window_id, button, x, y)
