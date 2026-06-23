"""Window client-area geometry — frame insets and client-relative point mapping.

``window_capture.get_window_geometry`` returns a window's outer bounding box (for
screenshotting), but there is no *client*-area rect, no frame-inset math, and no
client→screen point mapping. RPA needs "click at ``(x, y)`` *inside* this window's
client area regardless of title-bar height / borders" — the building block for
window-relative clicking. This adds the client rect, the pure frame-inset and
client-to-screen helpers, and a one-call ``client_point``.

``frame_insets`` / ``client_to_screen`` are pure geometry (headless-testable); only
``get_client_rect``'s default reader touches Win32 (``GetClientRect`` +
``ClientToScreen``), and it is injectable. Imports no ``PySide6``.
"""
import sys
from typing import Callable, Dict, Optional, Tuple

Rect = Tuple[int, int, int, int]
RectReader = Callable[[str], Optional[Rect]]


def frame_insets(window_rect: Rect, client_rect: Rect) -> Dict[str, int]:
    """Return the border / title-bar thickness as ``{left, top, right, bottom}``.

    Both rects are ``(x, y, width, height)`` in screen coordinates; the client rect is
    inset within the window rect by the frame.
    """
    wx, wy, ww, wh = (int(v) for v in window_rect[:4])
    cx, cy, cw, ch = (int(v) for v in client_rect[:4])
    return {"left": cx - wx, "top": cy - wy,
            "right": (wx + ww) - (cx + cw), "bottom": (wy + wh) - (cy + ch)}


def client_to_screen(client_rect: Rect, x: int, y: int) -> Tuple[int, int]:
    """Map a client-area-local point to absolute screen coordinates."""
    return (int(client_rect[0]) + int(x), int(client_rect[1]) + int(y))


def _default_client_reader(title: str) -> Optional[Rect]:
    """Read a window's client rect in screen coordinates (Win32 only)."""
    if not sys.platform.startswith("win"):
        return None
    from je_auto_control.wrapper.auto_control_window import find_window
    hit = find_window(title)
    if hit is None:
        return None
    import ctypes
    from ctypes import wintypes
    hwnd = int(hit[0])
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    origin = wintypes.POINT(0, 0)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return (origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top)


def get_client_rect(title: str, *,
                    reader: Optional[RectReader] = None) -> Optional[Rect]:
    """Return ``(x, y, width, height)`` of a window's client area (or ``None``).

    The origin is in screen coordinates. ``reader`` is injectable for tests; the
    default uses Win32 and returns ``None`` on other platforms.
    """
    return (reader or _default_client_reader)(title)


def client_point(title: str, x: int, y: int, *,
                 reader: Optional[RectReader] = None) -> Optional[Tuple[int, int]]:
    """Return the screen point for a client-area-local ``(x, y)`` (or ``None``).

    Lets you click at a position *inside* the window regardless of its title-bar /
    border thickness.
    """
    rect = get_client_rect(title, reader=reader)
    return client_to_screen(rect, x, y) if rect is not None else None
