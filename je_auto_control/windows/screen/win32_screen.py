import sys
from typing import List, Tuple

from je_auto_control.utils.exception.exception_tags import windows_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# 僅允許在 Windows 平台使用 Only allow on Windows platform
if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

import ctypes

# 初始化 Win32 API 函式 Initialize Win32 API functions
_user32 = ctypes.windll.user32
_user32.SetProcessDPIAware()  # 確保 DPI 感知，避免座標偏移
_gdi32 = ctypes.windll.gdi32


def size() -> List[int]:
    """
    取得螢幕大小
    Get screen size

    :return: [width, height]
    """
    return [_user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)]


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
        raise RuntimeError("GetDC failed")

    try:
        pixel = _gdi32.GetPixel(dc, x, y)
        if pixel == 0xFFFFFFFF:  # GetPixel 失敗時回傳 -1 (0xFFFFFFFF)
            raise RuntimeError("GetPixel failed")

        r = pixel & 0xFF
        g = (pixel >> 8) & 0xFF
        b = (pixel >> 16) & 0xFF
        return r, g, b
    finally:
        _user32.ReleaseDC(hwnd, dc)