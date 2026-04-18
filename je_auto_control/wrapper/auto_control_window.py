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


def list_windows() -> List[Tuple[int, str]]:
    """Return a list of ``(hwnd, title)`` for every visible top-level window."""
    _require_windows()
    from je_auto_control.windows.window import windows_window_manage as wm
    return wm.get_all_window_hwnd()


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
    """Minimise the first matching window."""
    _require_windows()
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    from je_auto_control.windows.window import windows_window_manage as wm
    return wm.close_window(hit[0])


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
