"""Abstract window-management backend."""
from typing import List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import (
    AutoControlUnsupportedOperationException,
)


class WindowManageBackend:
    """One platform's answers about its top-level windows.

    Everything that is not platform-specific — substring matching, waiting,
    "move without restating the size" — lives in
    :mod:`je_auto_control.wrapper.auto_control_window`, so a backend only has
    to list windows and answer about one at a time.

    ``window_id`` is whatever the platform calls a window: an ``HWND`` on
    Windows, an X11 window id on Linux, a ``CGWindowID`` on macOS. It is
    always a plain ``int``, so it composes with any other call on that
    platform.

    A backend that cannot perform an operation raises through
    :meth:`_unsupported` rather than returning a falsy value: "this platform
    has no such concept" and "it did not work this time" are different
    answers, and a caller that cannot tell them apart will retry forever.
    """

    name: str = "abstract"
    available: bool = False

    # --- listing -----------------------------------------------------------

    def list_windows(self) -> List[Tuple[int, str]]:
        """``(window_id, title)`` for every visible top-level window.

        Front-most first, so the first match of a title substring is the one
        the user is most likely to mean.
        """
        raise NotImplementedError

    def foreground_window(self) -> int:
        """The window the user is working in, or ``0`` when there is none."""
        self._unsupported("foreground_window")

    # --- reading one window ------------------------------------------------

    def window_rect(self, window_id: int,
                    ) -> Optional[Tuple[int, int, int, int]]:
        """``(left, top, right, bottom)`` in screen coordinates, or None.

        Screen coordinates, so on a multi-monitor desktop these can be
        negative for a monitor left of or above the primary one.
        """
        self._unsupported("window_rect")

    def window_process_id(self, window_id: int) -> int:
        """The pid owning the window, or ``0`` when it cannot be determined.

        A title is not identity — applications rewrite theirs at will and
        unrelated programs share names like ``Settings`` — so ownership is
        what addresses a window stably.
        """
        self._unsupported("window_process_id")

    def is_minimized(self, window_id: int) -> bool:
        """Whether the window is minimised / iconified."""
        self._unsupported("is_minimized")

    # --- acting on one window ----------------------------------------------

    def set_foreground(self, window_id: int) -> None:
        """Raise the window and give it the keyboard focus."""
        self._unsupported("set_foreground")

    def restore(self, window_id: int) -> None:
        """Un-minimise the window without changing anything else.

        Deliberately not "show it however": restoring a *maximised* window
        would un-maximise it, which is not what focusing something should do.
        """
        self._unsupported("restore")

    def show(self, window_id: int, cmd_show: int) -> None:
        """Apply a platform show-state code (Win32 ``ShowWindow`` numbering)."""
        self._unsupported("show")

    def close(self, window_id: int) -> bool:
        """Ask the window to close; ``False`` when the request was refused."""
        self._unsupported("close")

    def minimize(self, window_id: int) -> bool:
        """Minimise the window; ``False`` when the request was refused."""
        self._unsupported("minimize")

    def move(self, window_id: int, x: int, y: int,
             width: int, height: int) -> bool:
        """Move and resize the window; ``False`` when the request was refused."""
        self._unsupported("move")

    # --- acting on a window that does not have focus -----------------------

    def post_key(self, window_id: int, keycode: int,
                 character: str = "") -> bool:
        """Deliver one key to the window without focusing it."""
        self._unsupported("post_key")

    def post_click(self, window_id: int, button: str, x: int, y: int) -> bool:
        """Deliver one click to the window without focusing it.

        ``x`` / ``y`` are relative to the window's own top-left corner.
        """
        self._unsupported("post_click")

    # --- refusal -----------------------------------------------------------

    def _unsupported(self, operation: str):
        """Raise a clear error naming what this backend cannot do."""
        raise AutoControlUnsupportedOperationException(
            f"{operation} is not supported by the {self.name} window backend",
        )
