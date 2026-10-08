"""Capture a specific window, and snapshot / restore window layouts.

``screenshot`` only grabs the whole screen or a coordinate region; here
we resolve a window's geometry by title and screenshot exactly its
bounds, plus save every window's position and move them all back later
(handy for test setup / teardown).

Window geometry is read per-platform — on Windows via Win32; other
platforms return ``None`` for now. Two rectangles are in play there and they
are not interchangeable: a capture wants the *visible* frame (DWM's extended
frame bounds), a saved layout wants ``GetWindowRect``, because that is the
rectangle ``MoveWindow`` positions. It includes the invisible resize borders
of Windows 10 / 11, so restoring the visible frame through ``MoveWindow``
moved every window 7 px right and shrank it by 14 x 7 px on each round.

Snap, grid and cascade lay windows out in the primary monitor's work area
(the screen minus the taskbar), not the whole screen.

The geometry / capture / list / move operations are all injectable so the
logic is fully unit-testable without real windows. GUI-free.
"""
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

Rect = Tuple[int, int, int, int]
GeometryProvider = Callable[[str], Optional[Rect]]
WindowLister = Callable[[], List[Tuple[int, str]]]
WindowMover = Callable[[str, int, int, int, int], bool]
SizeProvider = Callable[[], Tuple[int, int]]
AreaProvider = Callable[[], Tuple[int, int, int, int]]


def get_window_geometry(title: str,
                        case_sensitive: bool = False) -> Optional[Rect]:
    """Return ``(x, y, width, height)`` of the first window matching ``title``.

    Windows-only for now (Win32 ``GetWindowRect``); returns ``None`` on
    other platforms or when no window matches.
    """
    from je_auto_control.wrapper.auto_control_window import find_window
    hit = find_window(title, case_sensitive=case_sensitive)
    if hit is None or sys.platform != "win32":
        return None
    return _win32_geometry(int(hit[0]))


def _win32_geometry(hwnd: int) -> Optional[Rect]:
    import ctypes
    from ctypes import wintypes
    rect = wintypes.RECT()
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]  # reason: win32-only ctypes
    if user32.IsIconic(hwnd):
        # A minimized window sits at (-32000, -32000); capturing that rect
        # returned whatever was there instead of the window.
        return None
    # The DWM frame bounds are the visible window; GetWindowRect includes
    # the ~7 px invisible resize borders on Windows 10 / 11.
    dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]  # reason: win32-only ctypes
    if dwmapi.DwmGetWindowAttribute(hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect),
                                    ctypes.sizeof(rect)) != 0 \
            and not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return (rect.left, rect.top,
            rect.right - rect.left, rect.bottom - rect.top)


_DWMWA_EXTENDED_FRAME_BOUNDS = 9
_SPI_GETWORKAREA = 0x0030


def _win32_window_rect(hwnd: int) -> Optional[Rect]:
    """``GetWindowRect`` as ``(x, y, width, height)``: what ``MoveWindow`` takes back."""
    import ctypes
    from ctypes import wintypes
    rect = wintypes.RECT()
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]  # reason: win32-only ctypes
    if user32.IsIconic(hwnd) or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        # A minimized window sits at (-32000, -32000); saving that would
        # "restore" it off every screen.
        return None
    return (rect.left, rect.top,
            rect.right - rect.left, rect.bottom - rect.top)


def _win32_work_area() -> Optional[Rect]:
    """The primary monitor's work area as ``(x, y, width, height)``, or ``None``."""
    import ctypes
    from ctypes import wintypes
    rect = wintypes.RECT()
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]  # reason: win32-only ctypes
    if not user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    return (rect.left, rect.top, width, height) if width > 0 and height > 0 else None


def _default_capture(output_path: str, rect: Rect) -> None:
    from je_auto_control.wrapper.auto_control_screen import screenshot
    x, y, width, height = rect
    screenshot(str(output_path), screen_region=[x, y, x + width, y + height])


def capture_window(title: str, output_path: Union[str, Path], *,
                   geometry: Optional[GeometryProvider] = None,
                   capture: Optional[Callable[[str, Rect], None]] = None
                   ) -> Optional[str]:
    """Screenshot the window matching ``title`` to ``output_path``.

    Returns the output path, or ``None`` when the window has no readable
    geometry. ``geometry`` / ``capture`` are injectable for tests.
    """
    provider = geometry or get_window_geometry
    rect = provider(title)
    if rect is None:
        return None
    (capture or _default_capture)(str(output_path), rect)
    return str(output_path)


def _default_lister() -> List[Tuple[int, str]]:
    """Titled windows only — an untitled one cannot be restored.

    ``restore_window_layout`` addresses a window by its title, so an entry with
    a blank one is skipped there; saving them anyway made the two disagree on
    how many windows a layout contains. On a real desktop that is roughly half
    the entries (measured here: 28 saved, 15 restorable), so a caller reporting
    the saved count was over-promising by a factor of two.
    """
    from je_auto_control.wrapper.auto_control_window import list_windows
    return list_windows(titled_only=True)


def save_window_layout(path: Optional[Union[str, Path]] = None, *,
                       lister: Optional[WindowLister] = None,
                       geometry: Optional[GeometryProvider] = None
                       ) -> List[Dict[str, Any]]:
    """Snapshot the geometry of every titled window.

    Returns a list of ``{title, x, y, width, height}`` and, when ``path``
    is given, also writes it as JSON for a later
    :func:`restore_window_layout`. Windows with no readable geometry are
    skipped.

    The rectangle is the one ``MoveWindow`` positions (``GetWindowRect``), so
    saving and restoring leaves a window exactly where it was. A layout file
    written before this held the visible frame instead and still restores
    7 px off; save it again.
    """
    layout: List[Dict[str, Any]] = []
    for hwnd, title in (lister or _default_lister)():
        # By handle, which the lister already has: looking the window up
        # again by title substring read another window's geometry whenever
        # one title contained another or two windows shared a title.
        rect = geometry(title) if geometry is not None else _handle_geometry(hwnd)
        if rect is None:
            continue
        layout.append({"title": title, "x": rect[0], "y": rect[1],
                       "width": rect[2], "height": rect[3]})
    if path is not None:
        Path(path).write_text(json.dumps(layout, indent=2), encoding="utf-8")
    return layout


def _default_mover(title: str, x: int, y: int,
                   width: int, height: int) -> bool:
    """Move the first window whose title contains ``title`` (snap / grid / cascade).

    Those take titles a user typed, often partial. A saved layout holds exact
    titles and uses :func:`_exact_title_mover` instead.
    """
    from je_auto_control.wrapper.auto_control_window import find_window
    hit = find_window(title)
    if hit is None or sys.platform != "win32":
        return False
    from je_auto_control.windows.window import windows_window_manage as wm
    return bool(wm.move_window(int(hit[0]), x, y, width, height))


def _handle_geometry(hwnd: int) -> Optional[Rect]:
    """The rectangle a layout stores for ``hwnd``: the one the mover takes."""
    return _win32_window_rect(int(hwnd)) if sys.platform == "win32" else None


def _exact_title_mover() -> WindowMover:
    """A mover that gives each saved entry a different window of that exact title.

    It matched by title substring, so every entry whose title another
    window's title contained -- and every duplicate title -- moved the same
    first window, leaving the others where they were.
    """
    used: set = set()

    def move(title: str, x: int, y: int, width: int, height: int) -> bool:
        if sys.platform != "win32":
            return False
        from je_auto_control.wrapper.auto_control_window import list_windows
        from je_auto_control.windows.window import windows_window_manage as wm
        for hwnd, name in list_windows(titled_only=True):
            if name == title and hwnd not in used:
                used.add(hwnd)
                return bool(wm.move_window(int(hwnd), x, y, width, height))
        return False

    return move


def restore_window_layout(layout: Union[List[Dict[str, Any]], str, Path], *,
                          mover: Optional[WindowMover] = None) -> int:
    """Move each window back to its saved geometry; return the count moved.

    ``layout`` is a list from :func:`save_window_layout`, or a path to the
    JSON it wrote. ``mover`` is injectable for tests.
    """
    entries: List[Dict[str, Any]] = (
        json.loads(Path(layout).read_text(encoding="utf-8"))
        if isinstance(layout, (str, Path)) else list(layout)
    )
    move = mover or _exact_title_mover()
    restored = 0
    for entry in entries:
        title = entry.get("title")
        if title and move(title, int(entry["x"]), int(entry["y"]),
                          int(entry["width"]), int(entry["height"])):
            restored += 1
    return restored


def _snap_rect(position: str, width: int, height: int,
               origin: Tuple[int, int] = (0, 0)) -> Rect:
    half_w = width // 2
    half_h = height // 2
    regions = {
        "left": (0, 0, half_w, height),
        "right": (half_w, 0, width - half_w, height),
        "top": (0, 0, width, half_h),
        "bottom": (0, half_h, width, height - half_h),
        "top-left": (0, 0, half_w, half_h),
        "top-right": (half_w, 0, width - half_w, half_h),
        "bottom-left": (0, half_h, half_w, height - half_h),
        "bottom-right": (half_w, half_h, width - half_w, height - half_h),
        "max": (0, 0, width, height),
    }
    rect = regions.get(str(position).lower())
    if rect is None:
        raise ValueError(
            f"unknown snap position {position!r}; "
            f"expected one of {sorted(regions)}",
        )
    return (origin[0] + rect[0], origin[1] + rect[1], rect[2], rect[3])


def _default_screen_size() -> Tuple[int, int]:
    from je_auto_control.wrapper.auto_control_screen import screen_size
    size = screen_size()
    return (int(size[0]), int(size[1]))


def _default_work_area() -> Rect:
    """Where windows may be laid out: the work area, else the whole screen."""
    area = _win32_work_area() if sys.platform == "win32" else None
    if area is not None:
        return area
    width, height = _default_screen_size()
    return (0, 0, width, height)


def _layout_area(screen_size: Optional[SizeProvider],
                 work_area: Optional[AreaProvider]) -> Rect:
    """The ``(x, y, width, height)`` to lay out in, from whichever provider was given.

    ``screen_size`` only knows a size, so it means "this size, at the origin";
    with neither, the work area is asked for.
    """
    if work_area is not None:
        x, y, width, height = work_area()
        return (int(x), int(y), int(width), int(height))
    if screen_size is not None:
        width, height = screen_size()
        return (0, 0, int(width), int(height))
    return _default_work_area()


def snap_window(title: str, position: str = "left", *,
                mover: Optional[WindowMover] = None,
                screen_size: Optional[SizeProvider] = None,
                work_area: Optional[AreaProvider] = None) -> bool:
    """Move/resize the window matching ``title`` to a region of the work area.

    ``position`` is one of left / right / top / bottom / top-left /
    top-right / bottom-left / bottom-right / max. Returns ``True`` when the
    window moved. The region is cut from the work area (the screen minus the
    taskbar), so the bottom of a snapped window is no longer under the
    taskbar. ``work_area`` (``() -> (x, y, width, height)``), ``screen_size``
    and the mover are injectable for tests.
    """
    left, top, width, height = _layout_area(screen_size, work_area)
    x, y, w, h = _snap_rect(position, width, height, (left, top))
    return (mover or _default_mover)(title, x, y, w, h)


def _move_into(titles: List[str], rects, move: WindowMover) -> int:
    """Move each title to the matching rectangle; return the number moved."""
    moved = 0
    for title, rect in zip(titles, rects):
        if move(title, rect.x, rect.y, rect.width, rect.height):
            moved += 1
    return moved


def _grid_shape(count: int, rows: Optional[int],
                cols: Optional[int]) -> Tuple[int, int]:
    """Resolve the (rows, cols) grid shape, auto-sizing to near-square when unset."""
    if rows and cols:
        return int(rows), int(cols)
    if cols:
        return math.ceil(count / int(cols)), int(cols)
    if rows:
        return int(rows), math.ceil(count / int(rows))
    side = math.ceil(math.sqrt(count))
    return math.ceil(count / side), side


def arrange_grid(titles: List[str], *, rows: Optional[int] = None,
                 cols: Optional[int] = None, gap: int = 0,
                 mover: Optional[WindowMover] = None,
                 screen_size: Optional[SizeProvider] = None,
                 work_area: Optional[AreaProvider] = None) -> int:
    """Tile the given window ``titles`` into a grid; return the count moved.

    ``rows`` / ``cols`` default to a near-square auto-shape for the number of
    windows; ``gap`` spaces the cells. The grid fills the work area (the screen
    minus the taskbar). The mover and the size / work-area providers are
    injectable for tests. Windows beyond the grid capacity are left untouched.
    """
    from je_auto_control.utils.window_layout import grid_rects
    titles = list(titles)
    if not titles:
        return 0
    grid_rows, grid_cols = _grid_shape(len(titles), rows, cols)
    rects = grid_rects(_layout_area(screen_size, work_area), grid_rows, grid_cols,
                       gap=int(gap))
    return _move_into(titles, rects, mover or _default_mover)


def arrange_cascade(titles: List[str], *, offset: int = 30,
                    mover: Optional[WindowMover] = None,
                    screen_size: Optional[SizeProvider] = None,
                    work_area: Optional[AreaProvider] = None) -> int:
    """Cascade the given window ``titles`` diagonally; return the count moved.

    Each window is ``offset`` pixels down-right of the previous, sized to 60% of
    the work area and clamped inside it. The mover and the size / work-area
    providers are injectable.
    """
    from je_auto_control.utils.window_layout import cascade_rects
    titles = list(titles)
    if not titles:
        return 0
    rects = cascade_rects(_layout_area(screen_size, work_area), len(titles),
                          offset=int(offset))
    return _move_into(titles, rects, mover or _default_mover)
