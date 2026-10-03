"""Capture a specific window, and snapshot / restore window layouts.

``screenshot`` only grabs the whole screen or a coordinate region; here
we resolve a window's geometry by title and screenshot exactly its
bounds, plus save every window's position and move them all back later
(handy for test setup / teardown).

Window geometry is read per-platform — on Windows via the Win32
``GetWindowRect`` API; other platforms return ``None`` for now. The
geometry / capture / list / move operations are all injectable so the
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


def _default_capture(output_path: str, rect: Rect) -> None:
    """Capture global input coordinates, including negative secondary displays."""
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

    Returns ``{title, x, y, width, height}`` entries; native Windows snapshots
    also carry ``placement`` with normal bounds and the show state. When ``path``
    is given, also writes it as JSON for a later
    :func:`restore_window_layout`. Windows with no readable geometry are
    skipped. Injecting ``geometry`` preserves the geometry-only format.
    """
    layout: List[Dict[str, Any]] = []
    for hwnd, title in (lister or _default_lister)():
        # By handle, which the lister already has: looking the window up
        # again by title substring read another window's geometry whenever
        # one title contained another or two windows shared a title.
        rect = geometry(title) if geometry is not None else _handle_geometry(hwnd)
        if rect is None:
            continue
        entry = {"title": title, "x": rect[0], "y": rect[1], "width": rect[2], "height": rect[3]}
        if geometry is None and sys.platform == "win32":
            from je_auto_control.windows.window import windows_window_manage as wm
            placement = wm.get_window_placement(int(hwnd))
            if placement is not None:
                entry["placement"] = placement
        layout.append(entry)
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
    if sys.platform != "win32":
        return None
    from je_auto_control.windows.window import windows_window_manage as wm
    rect = wm.get_window_rect(int(hwnd))
    if rect is None:
        return None
    left, top, right, bottom = rect
    return left, top, right - left, bottom - top


def _exact_title_mover(placements: Optional[Dict[str, list]] = None) -> WindowMover:
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
                saved = (placements or {}).get(title)
                placement = saved.pop(0) if saved else None
                if placement is not None:
                    return wm.set_window_placement(int(hwnd), placement)
                return bool(wm.move_window(int(hwnd), x, y, width, height))
        return False

    return move


def restore_window_layout(layout: Union[List[Dict[str, Any]], str, Path], *,
                          mover: Optional[WindowMover] = None) -> int:
    """Restore native placement or legacy geometry; return the count restored.

    ``layout`` is a list from :func:`save_window_layout`, or a path to the
    JSON it wrote. Native Windows entries replay placement and show state;
    legacy entries use MoveWindow. Injected ``mover`` receives geometry only.
    """
    entries: List[Dict[str, Any]] = (
        json.loads(Path(layout).read_text(encoding="utf-8"))
        if isinstance(layout, (str, Path)) else list(layout)
    )
    placements: Dict[str, list] = {}
    for entry in entries:
        placements.setdefault(entry.get("title", ""), []).append(entry.get("placement"))
    move = mover or _exact_title_mover(placements)
    restored = 0
    for entry in entries:
        title = entry.get("title")
        if title and move(title, int(entry["x"]), int(entry["y"]),
                          int(entry["width"]), int(entry["height"])):
            restored += 1
    return restored


def _snap_rect(position: str, width: int, height: int) -> Rect:
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
    return rect


def _default_screen_size() -> Tuple[int, int]:
    from je_auto_control.wrapper.auto_control_screen import screen_size
    size = screen_size()
    return (int(size[0]), int(size[1]))


def _layout_area(screen_size: Optional[SizeProvider]) -> Rect:
    """Use explicit size providers as-is, otherwise the Windows work area."""
    if screen_size is None and sys.platform == "win32":
        from je_auto_control.windows.window import windows_window_manage as wm
        area = wm.get_work_area()
        if area is not None:
            left, top, right, bottom = area
            return left, top, right - left, bottom - top
    width, height = (screen_size or _default_screen_size)()
    return 0, 0, int(width), int(height)


def snap_window(title: str, position: str = "left", *,
                mover: Optional[WindowMover] = None,
                screen_size: Optional[SizeProvider] = None) -> bool:
    """Move/resize the window matching ``title`` to a screen region.

    ``position`` is one of left / right / top / bottom / top-left /
    top-right / bottom-left / bottom-right / max. Returns ``True`` when the
    window moved. The size provider and mover are injectable for tests.
    """
    left, top, width, height = _layout_area(screen_size)
    x, y, w, h = _snap_rect(position, width, height)
    return (mover or _default_mover)(title, left + x, top + y, w, h)


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
                 screen_size: Optional[SizeProvider] = None) -> int:
    """Tile the given window ``titles`` into a grid; return the count moved.

    ``rows`` / ``cols`` default to a near-square auto-shape for the number of
    windows; ``gap`` spaces the cells. The mover and size provider are injectable
    for tests. Windows beyond the grid capacity are left untouched.
    """
    from je_auto_control.utils.window_layout import grid_rects
    titles = list(titles)
    if not titles:
        return 0
    grid_rows, grid_cols = _grid_shape(len(titles), rows, cols)
    rects = grid_rects(_layout_area(screen_size), grid_rows, grid_cols,
                       gap=int(gap))
    return _move_into(titles, rects, mover or _default_mover)


def arrange_cascade(titles: List[str], *, offset: int = 30,
                    mover: Optional[WindowMover] = None,
                    screen_size: Optional[SizeProvider] = None) -> int:
    """Cascade the given window ``titles`` diagonally; return the count moved.

    Each window is ``offset`` pixels down-right of the previous, sized to 60% of
    the work area and clamped on-screen. The mover and size provider are injectable.
    """
    from je_auto_control.utils.window_layout import cascade_rects
    titles = list(titles)
    if not titles:
        return 0
    rects = cascade_rects(_layout_area(screen_size), len(titles),
                          offset=int(offset))
    return _move_into(titles, rects, mover or _default_mover)
