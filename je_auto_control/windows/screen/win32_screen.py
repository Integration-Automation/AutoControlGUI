import sys
from typing import Tuple

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
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

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

# 確保 DPI 感知，避免座標偏移。**這是行程層級的副作用**，而它發生在 import 時：
# 一旦設定就無法還原，之後所有 Win32 座標查詢都會拿到實體像素。這正是本模組被
# import 的理由（螢幕尺寸與取色都必須是實體座標），但呼叫端要知道它會影響整個
# 行程——擷取與滑鼠座標的換算請走 `utils/monitor_layout`。
#
# Process-wide and irreversible, and it happens at import time; conversions
# between physical and logical coordinates belong to ``utils/monitor_layout``.
_user32.SetProcessDPIAware()

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
