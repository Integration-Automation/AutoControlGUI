import sys
from typing import List, Union, Tuple

from je_auto_control.utils.exception.exception_tags import windows_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error)

import ctypes

_user32: ctypes.windll.user32 = ctypes.windll.user32
_user32.SetProcessDPIAware()
_gdi32 = ctypes.windll.gdi32


def size() -> List[Union[int, int]]:
    """
    get screen size
    """
    return [_user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)]


def get_pixel(x: int, y: int, hwnd: int = 0) -> Tuple[int, int, int]:
    dc = _user32.GetDC(hwnd)
    if not dc:
        raise RuntimeError("GetDC failed")

    try:
        pixel = _gdi32.GetPixel(dc, x, y)
        if pixel == 0xFFFFFFFF:
            raise RuntimeError("GetPixel failed")

        r = pixel & 0xFF
        g = (pixel >> 8) & 0xFF
        b = (pixel >> 16) & 0xFF
        return r, g, b
    finally:
        _user32.ReleaseDC(hwnd, dc)

