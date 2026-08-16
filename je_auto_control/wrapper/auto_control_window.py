"""Cross-platform window management facade.

On Windows, delegates to ``windows_window_manage`` (Win32 API).
On macOS / Linux, operations raise a clear ``NotImplementedError``.
"""
import sys
import time
from typing import List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_IS_WINDOWS = sys.platform in ("win32", "cygwin", "msys")


def _require_windows() -> None:
    if not _IS_WINDOWS:
        raise NotImplementedError(
            f"Window management is only implemented on Windows (got {sys.platform})"
        )


def list_windows(titled_only: bool = False) -> List[Tuple[int, str]]:
    """Return ``(hwnd, title)`` for every visible top-level window, front-most
    first.

    ``hwnd`` is a plain ``int``, so it composes with any other Win32 call.
    Most visible windows have no title (shell and helper surfaces); pass
    ``titled_only`` for just the ones a user would recognise.
    """
    _require_windows()
    from je_auto_control.windows.window import windows_window_manage as wm
    found = wm.get_all_window_hwnd()
    if titled_only:
        return [(hwnd, title) for hwnd, title in found if title.strip()]
    return found


def find_window(title_substring: str,
                case_sensitive: bool = False) -> Optional[Tuple[int, str]]:
    """Return the first window whose title contains ``title_substring``."""
    needle = title_substring if case_sensitive else title_substring.lower()
    for hwnd, title in list_windows():
        haystack = title if case_sensitive else title.lower()
        if needle in haystack:
            return hwnd, title
    return None


def focus_window(title_substring: str, case_sensitive: bool = False) -> int:
    """Bring the first matching window to the foreground; return its hwnd."""
    _require_windows()
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        raise AutoControlActionException(
            f"focus_window: no window matches {title_substring!r}"
        )
    hwnd, title = hit
    from je_auto_control.windows.window import windows_window_manage as wm
    # A minimized window stays invisible however often you foreground it, so
    # restore it first — but only when it really is minimized: SW_RESTORE on a
    # maximized window un-maximizes it, which is not what "focus" should do.
    if wm.is_window_minimized(hwnd):
        wm.show_window(hwnd, wm.SW_RESTORE)
    wm.set_foreground_window(hwnd)
    autocontrol_logger.info("focused window hwnd=%s title=%r", hwnd, title)
    return hwnd


def wait_for_window(title_substring: str,
                    timeout: float = 10.0,
                    poll: float = 0.5,
                    case_sensitive: bool = False) -> int:
    """Poll until a window with the given title appears; return its hwnd."""
    _require_windows()
    poll = max(0.05, float(poll))
    deadline = time.monotonic() + float(timeout)
    while time.monotonic() < deadline:
        hit = find_window(title_substring, case_sensitive)
        if hit is not None:
            return hit[0]
        time.sleep(poll)
    raise AutoControlActionException(
        f"wait_for_window timeout: {title_substring!r}"
    )


def close_window_by_title(title_substring: str, case_sensitive: bool = False) -> bool:
    """Ask the first matching window to close. ``False`` if nothing matched.

    **Behaviour change**: this used to *minimise* the window, because the Win32
    call underneath is named ``CloseWindow`` but minimises. Use
    :func:`minimize_window_by_title` for the old behaviour.
    """
    _require_windows()
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    from je_auto_control.windows.window import windows_window_manage as wm
    return wm.close_window(hit[0])


def minimize_window_by_title(title_substring: str,
                             case_sensitive: bool = False) -> bool:
    """Minimise the first matching window. ``False`` if nothing matched."""
    _require_windows()
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    from je_auto_control.windows.window import windows_window_manage as wm
    return wm.minimize_window(hit[0])


def foreground_window() -> Optional[Tuple[int, str]]:
    """The window the user is currently working in, or ``None``."""
    _require_windows()
    from je_auto_control.windows.window import windows_window_manage as wm
    hwnd = wm.get_foreground_window()
    if not hwnd:
        return None
    titles = dict(wm.get_all_window_hwnd())
    return hwnd, titles.get(hwnd, "")


def window_rect(title_substring: str,
                case_sensitive: bool = False,
                ) -> Optional[Tuple[int, int, int, int]]:
    """``(left, top, right, bottom)`` of the first matching window.

    Screen coordinates, so on a multi-monitor desktop the values can be
    negative for a monitor left of or above the primary one.
    """
    _require_windows()
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return None
    from je_auto_control.windows.window import windows_window_manage as wm
    return wm.get_window_rect(hit[0])


def move_window_by_title(title_substring: str, x: int, y: int,
                         width: Optional[int] = None,
                         height: Optional[int] = None,
                         case_sensitive: bool = False) -> bool:
    """Move (and optionally resize) the first matching window.

    Omitting ``width`` / ``height`` keeps the window's current size, so a plain
    reposition does not have to restate dimensions the caller has to look up.
    """
    _require_windows()
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    from je_auto_control.windows.window import windows_window_manage as wm
    if width is None or height is None:
        rect = wm.get_window_rect(hit[0])
        if rect is None:
            return False
        left, top, right, bottom = rect
        width = right - left if width is None else width
        height = bottom - top if height is None else height
    return wm.move_window(hit[0], int(x), int(y), int(width), int(height))


def show_window_by_title(title_substring: str, cmd_show: int = 1,
                         case_sensitive: bool = False) -> bool:
    """Show or restore a window (``cmd_show`` follows Win32 ShowWindow)."""
    _require_windows()
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    from je_auto_control.windows.window import windows_window_manage as wm
    wm.show_window(hit[0], int(cmd_show))
    return True
