"""Cross-platform window management facade.

On Windows, delegates to ``windows_window_manage`` (Win32 API).
On macOS / Linux, operations raise a clear ``NotImplementedError``.
"""
import sys
import time
from typing import List, Optional, Tuple, Union

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


def post_key_to_window(title_substring: str, key: Union[int, str],
                       case_sensitive: bool = False) -> bool:
    """Type one key into a window **without focusing it**. ``False`` if no match.

    Unlike :func:`send_key_event_to_window` this resolves the window by
    substring (like every other function here) and posts to the control that
    actually has keyboard focus. Posting to the top-level frame — what the older
    function does — types nothing in any application with child controls;
    measured on Character Map, the frame swallowed the key and the focused edit
    accepted it.

    **This is best effort, not input.** ``PostMessage`` returning true means the
    message reached a queue, not that the application acted on it: games,
    anything reading raw input, and applications that check whether they are in
    the foreground all ignore posted messages. Callers must say so rather than
    reporting success.
    """
    _require_windows()
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    from je_auto_control.windows.window import windows_window_manage as wm
    keycode, character = _resolve_key(key)
    return wm.post_key(hit[0], keycode, character)


def post_click_to_window(title_substring: str, button: str = "left",
                         x: int = 0, y: int = 0,
                         case_sensitive: bool = False) -> bool:
    """Click inside a window **without focusing it**; ``False`` if no match.

    ``x`` / ``y`` are relative to the window's top-left corner. The click is
    posted to the deepest child control under that point, in that control's own
    client coordinates — a click posted to the frame lands nowhere. Same
    best-effort caveat as :func:`post_key_to_window`.
    """
    _require_windows()
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    from je_auto_control.windows.window import windows_window_manage as wm
    return wm.post_click(hit[0], _mouse_button_name(button), int(x), int(y))


def _resolve_key(key: Union[int, str]) -> Tuple[int, str]:
    """``(virtual key code, character to also post as WM_CHAR)``."""
    if isinstance(key, int):
        return int(key), ""
    name = str(key)
    from je_auto_control.wrapper.platform_wrapper import keyboard_keys_table
    keycode = keyboard_keys_table.get(name)
    if keycode is None:
        raise AutoControlActionException(f"unknown key name: {name!r}")
    # A one-character key is text: edit controls take their content from
    # WM_CHAR, so posting only the virtual-key messages types nothing.
    character = name if len(name) == 1 and name.isprintable() else ""
    return int(keycode), character


def _mouse_button_name(button: str) -> str:
    """Accept both plain and ``mouse_``-prefixed button names."""
    name = str(button).lower()
    return name[len("mouse_"):] if name.startswith("mouse_") else name


def foreground_window_process_id() -> Optional[int]:
    """The PID owning the foreground window, or ``None``.

    A window title is not identity: applications rewrite theirs at will, and
    unrelated programs share titles like ``Settings``. Callers that need to know
    *which program* the user is actually in front of — presence reporting,
    activity probes, "is my automation target focused" — have to go through the
    process id.
    """
    _require_windows()
    from je_auto_control.windows.window import windows_window_manage as wm
    hwnd = wm.get_foreground_window()
    if not hwnd:
        return None
    return wm.get_window_process_id(hwnd) or None


def window_process_id(title_substring: str,
                      case_sensitive: bool = False) -> Optional[int]:
    """The PID owning the first window whose title contains the substring."""
    _require_windows()
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return None
    from je_auto_control.windows.window import windows_window_manage as wm
    return wm.get_window_process_id(hit[0]) or None


def windows_for_process_id(pid: int,
                           titled_only: bool = False) -> List[Tuple[int, str]]:
    """Every visible top-level window owned by ``pid``.

    Titles cannot address a multi-process application: a browser's windows are
    named after whatever page they show, and several of its processes have no
    window at all. Ownership is the stable key.
    """
    _require_windows()
    from je_auto_control.windows.window import windows_window_manage as wm
    target = int(pid)
    return [(hwnd, title) for hwnd, title in list_windows(titled_only)
            if wm.get_window_process_id(hwnd) == target]


def minimize_windows_for_process(pid: int) -> int:
    """Minimise every visible top-level window owned by ``pid``; return the count."""
    _require_windows()
    from je_auto_control.windows.window import windows_window_manage as wm
    minimized = 0
    for hwnd, _title in windows_for_process_id(pid):
        if wm.minimize_window(hwnd):
            minimized += 1
    return minimized


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
