"""Cross-platform window management facade.

Delegates to whichever backend :mod:`je_auto_control.wrapper.window_backends`
selects — Win32 on Windows, EWMH over python-Xlib on X11, Quartz plus the
accessibility API on macOS — and keeps here everything that is not
platform-specific: substring matching, waiting, and the compositions like
"move without restating the size".

This was Windows-only for the project's whole life, which left these
functions, their 23 ``AC_*`` commands and their MCP tools dead on the two
other supported platforms. A platform with no backend still gets a null one
that lists nothing and refuses actions with a reason, so importing never
fails and callers get an answer rather than an ``ImportError``.
"""
import time
from typing import List, Optional, Tuple, Union

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.wrapper.window_backends import get_backend


def list_windows(titled_only: bool = False) -> List[Tuple[int, str]]:
    """Return ``(hwnd, title)`` for every visible top-level window, front-most
    first.

    ``hwnd`` is a plain ``int``, so it composes with any other Win32 call.
    Most visible windows have no title (shell and helper surfaces); pass
    ``titled_only`` for just the ones a user would recognise.
    """
    backend = get_backend()
    found = backend.list_windows()
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
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        raise AutoControlActionException(
            f"focus_window: no window matches {title_substring!r}"
        )
    hwnd, title = hit
    backend = get_backend()
    # A minimized window stays invisible however often you foreground it, so
    # restore it first — but only when it really is minimized: SW_RESTORE on a
    # maximized window un-maximizes it, which is not what "focus" should do.
    if backend.is_minimized(hwnd):
        backend.restore(hwnd)
    backend.set_foreground(hwnd)
    autocontrol_logger.info("focused window hwnd=%s title=%r", hwnd, title)
    return hwnd


def wait_for_window(title_substring: str,
                    timeout: float = 10.0,
                    poll: float = 0.5,
                    case_sensitive: bool = False) -> int:
    """Poll until a window with the given title appears; return its hwnd."""
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
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    backend = get_backend()
    return backend.close(hit[0])


def minimize_window_by_title(title_substring: str,
                             case_sensitive: bool = False) -> bool:
    """Minimise the first matching window. ``False`` if nothing matched."""
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    backend = get_backend()
    return backend.minimize(hit[0])


def foreground_window() -> Optional[Tuple[int, str]]:
    """The window the user is currently working in, or ``None``."""
    backend = get_backend()
    hwnd = backend.foreground_window()
    if not hwnd:
        return None
    titles = dict(backend.list_windows())
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
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    backend = get_backend()
    keycode, character = _resolve_key(key)
    return backend.post_key(hit[0], keycode, character)


def post_click_to_window(title_substring: str, button: str = "left",
                         x: int = 0, y: int = 0,
                         case_sensitive: bool = False) -> bool:
    """Click inside a window **without focusing it**; ``False`` if no match.

    ``x`` / ``y`` are relative to the window's top-left corner. The click is
    posted to the deepest child control under that point, in that control's own
    client coordinates — a click posted to the frame lands nowhere. Same
    best-effort caveat as :func:`post_key_to_window`.
    """
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    backend = get_backend()
    return backend.post_click(hit[0], _mouse_button_name(button), int(x), int(y))


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
    backend = get_backend()
    hwnd = backend.foreground_window()
    if not hwnd:
        return None
    return backend.window_process_id(hwnd) or None


def window_process_id(title_substring: str,
                      case_sensitive: bool = False) -> Optional[int]:
    """The PID owning the first window whose title contains the substring."""
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return None
    backend = get_backend()
    return backend.window_process_id(hit[0]) or None


def windows_for_process_id(pid: int,
                           titled_only: bool = False) -> List[Tuple[int, str]]:
    """Every visible top-level window owned by ``pid``.

    Titles cannot address a multi-process application: a browser's windows are
    named after whatever page they show, and several of its processes have no
    window at all. Ownership is the stable key.
    """
    backend = get_backend()
    target = int(pid)
    return [(hwnd, title) for hwnd, title in list_windows(titled_only)
            if backend.window_process_id(hwnd) == target]


def minimize_windows_for_process(pid: int) -> int:
    """Minimise every visible top-level window owned by ``pid``; return the count."""
    backend = get_backend()
    minimized = 0
    for hwnd, _title in windows_for_process_id(pid):
        if backend.minimize(hwnd):
            minimized += 1
    return minimized


def window_rect(title_substring: str,
                case_sensitive: bool = False,
                ) -> Optional[Tuple[int, int, int, int]]:
    """``(left, top, right, bottom)`` of the first matching window.

    Screen coordinates, so on a multi-monitor desktop the values can be
    negative for a monitor left of or above the primary one.
    """
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return None
    backend = get_backend()
    return backend.window_rect(hit[0])


def move_window_by_title(title_substring: str, x: int, y: int,
                         width: Optional[int] = None,
                         height: Optional[int] = None,
                         case_sensitive: bool = False) -> bool:
    """Move (and optionally resize) the first matching window.

    Omitting ``width`` / ``height`` keeps the window's current size, so a plain
    reposition does not have to restate dimensions the caller has to look up.
    """
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    backend = get_backend()
    if width is None or height is None:
        rect = backend.window_rect(hit[0])
        if rect is None:
            return False
        left, top, right, bottom = rect
        width = right - left if width is None else width
        height = bottom - top if height is None else height
    return backend.move(hit[0], int(x), int(y), int(width), int(height))


def show_window_by_title(title_substring: str, cmd_show: int = 1,
                         case_sensitive: bool = False) -> bool:
    """Show or restore a window (``cmd_show`` follows Win32 ShowWindow)."""
    hit = find_window(title_substring, case_sensitive)
    if hit is None:
        return False
    backend = get_backend()
    backend.show(hit[0], int(cmd_show))
    return True
