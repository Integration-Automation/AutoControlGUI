import sys
from typing import Any, Tuple

from je_auto_control.utils.exception.exception_tags import windows_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# 僅允許在 Windows 平台使用 Only allow on Windows platform
if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

import ctypes
from ctypes import wintypes

# 這個模組持有自己的 user32 / gdi32 handle，而不是共用 `ctypes.windll`：
# argtypes/restype 是設在**函式物件**上的，共用 handle 會讓這裡的原型外溢到
# 別的呼叫者（`utils/window_capture/` 就用自己的 RECT 呼叫 GetWindowRect）。
#
# This module owns its user32 / gdi32 handles rather than sharing
# ``ctypes.windll``: prototypes live on the function objects, so a shared handle
# would leak these declarations into every other caller in the process.
_user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]  # reason: win32-only ctypes
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)  # type: ignore[attr-defined]  # reason: win32-only ctypes

# HDC 是**指標寬度**的 handle。ctypes 預設把回傳值與參數當成 c_int，在 64 位元
# Windows 上會截斷——`GetDC` 回來就已經是壞的，再傳給 `GetPixel` / `ReleaseDC`
# 只會讓錯誤沉默地擴散（顏色讀錯、DC 沒被釋放）。與 `windows_window_manage` 的
# HWND、剪貼簿的 HGLOBAL 是同一個陷阱，所以每支都明寫原型。
#
# An HDC is a pointer-width handle and ctypes defaults to ``c_int``, which
# truncates it on 64-bit Windows: the value is already wrong coming out of
# ``GetDC``, and passing it on silently reads the wrong colour and leaks the DC.
_user32.SetProcessDPIAware.argtypes = []
_user32.SetProcessDPIAware.restype = wintypes.BOOL
_user32.GetSystemMetrics.argtypes = [ctypes.c_int]
_user32.GetSystemMetrics.restype = ctypes.c_int
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int
_gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.GetPixel.restype = wintypes.COLORREF

_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
_AWARENESS_NAMES = {0: "unaware", 1: "system", 2: "per_monitor"}
_dpi_awareness_requested = False


def _request_dpi_awareness(user32: Any) -> None:
    """Ask for per-monitor-v2 awareness, then system awareness; never raise."""
    try:
        setter = user32.SetProcessDpiAwarenessContext
        setter.argtypes = [ctypes.c_void_p]
        setter.restype = wintypes.BOOL
        if setter(ctypes.c_void_p(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)):
            return
    except (AttributeError, OSError):
        # Windows before 10 1703 exports no such function.
        pass
    try:
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def dpi_awareness(user32: Any = None) -> str:
    """
    這個行程實際的 DPI 感知：``unaware``／``system``／``per_monitor``／``unknown``
    The awareness this process really has: ``unaware`` / ``system`` /
    ``per_monitor`` / ``unknown``

    問系統而不是記住自己要求過什麼：行程的感知只能設定一次，host 程式、manifest
    或先建立的 Qt 可能早就決定了。
    Asked of the system rather than remembered: awareness can be set once per
    process, and a host application, a manifest or an earlier Qt may have
    decided it already.
    """
    library = user32 or _user32
    try:
        get_context = library.GetThreadDpiAwarenessContext
        get_context.argtypes = []
        get_context.restype = ctypes.c_void_p
        get_awareness = library.GetAwarenessFromDpiAwarenessContext
        get_awareness.argtypes = [ctypes.c_void_p]
        get_awareness.restype = ctypes.c_int
        return _AWARENESS_NAMES.get(int(get_awareness(get_context())), "unknown")
    except (AttributeError, OSError):
        return "unknown"


def enable_dpi_awareness(user32: Any = None) -> str:
    """
    讓行程成為 per-monitor v2 DPI 感知（做不到就退回系統感知）；回傳實際結果
    Make the process per-monitor-v2 DPI aware, falling back to system
    awareness; return what it ended up with

    **行程層級、無法還原，而且發生在 import 時**（本模組底下呼叫一次）。
    per-monitor 之後，每個螢幕的 Win32 座標、滑鼠座標與擷取到的像素都是該螢幕的
    實體像素。先前用的 `SetProcessDPIAware()` 是**系統**感知：只有 DPI 與主螢幕
    相同的螢幕是實體像素，其他螢幕被 Windows 虛擬化——座標被縮放、截圖是縮過的
    模糊影像。

    只要求一次：第二次呼叫不再碰 Win32，只回報現況。感知已被別人設定時（要求會
    被拒絕）不丟例外，照樣回報現況；那種行程裡擷取與滑鼠座標的換算仍由
    `utils/monitor_layout` 負責。

    Process-wide, irreversible, and it happens at import time (this module
    calls it once below). Once per-monitor, Win32 coordinates, mouse
    coordinates and captured pixels are each monitor's physical pixels. The
    ``SetProcessDPIAware()`` used before is *system* awareness: only monitors
    at the primary monitor's DPI were physical, and Windows virtualised the
    rest — scaled coordinates and a blurred, resized capture.

    Requested once: a second call does not touch Win32 and only reports. A
    process whose awareness someone else fixed first refuses the request; that
    is not an error, and ``utils/monitor_layout`` still converts between
    capture and mouse coordinates there.
    """
    global _dpi_awareness_requested
    library = user32 or _user32
    if not _dpi_awareness_requested:
        _dpi_awareness_requested = True
        _request_dpi_awareness(library)
    return dpi_awareness(library)


enable_dpi_awareness()

_CLR_INVALID = 0xFFFFFFFF


def size() -> Tuple[int, int]:
    """
    取得螢幕大小
    Get screen size

    一個 tuple，與 osx／x11／wayland 三個後端一致：這裡原本回 list，是四個
    後端裡唯一一個，而 `wrapper.auto_control_screen.screen_size` 對外承諾的
    是 tuple。每個呼叫端都只是解包成 width／height，所以型別對齊不改行為。
    The other three backends return a tuple and every caller unpacks the two
    values, so this was the odd one out against the seam's own contract.

    :return: (width, height)
    """
    return _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)


def get_pixel(x: int, y: int, hwnd: int = 0) -> Tuple[int, int, int]:
    """
    取得指定座標的像素顏色
    Get pixel color at given coordinates

    :param x: X 座標 X position
    :param y: Y 座標 Y position
    :param hwnd: 視窗 handle (預設為桌面) Window handle (default = desktop)
    :return: (R, G, B)
    """
    dc = _user32.GetDC(hwnd)
    if not dc:
        raise AutoControlException("GetDC failed")

    try:
        pixel = int(_gdi32.GetPixel(dc, int(x), int(y)))
        if pixel == _CLR_INVALID:      # GetPixel 失敗時回傳 CLR_INVALID
            raise AutoControlException("GetPixel failed")

        r = pixel & 0xFF
        g = (pixel >> 8) & 0xFF
        b = (pixel >> 16) & 0xFF
        return r, g, b
    finally:
        _user32.ReleaseDC(hwnd, dc)
