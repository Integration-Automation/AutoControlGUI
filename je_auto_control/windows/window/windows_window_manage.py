"""
Windows 視窗管理（Win32 ctypes）
Windows window management (Win32 ctypes)
"""
import ctypes
from ctypes import WINFUNCTYPE, byref, create_unicode_buffer, wintypes
from typing import List, Optional, Tuple

# 相容用途：舊版本從這個模組匯出共用的 user32。
# Compatibility: older code imported the shared user32 from this module.
from je_auto_control.windows.core.utils.win32_ctype_input import user32  # noqa: F401

# 這個模組刻意持有自己的 user32 handle，而不是共用上面那個：底下每個函式都要
# 設 argtypes/restype，而那是設在**函式物件**上的，共用同一個 handle 會讓設定
# 外溢到別的模組。例如 `utils/window_capture/` 用它自己的 RECT 呼叫
# `GetWindowRect`，若被這裡的 argtypes 綁死就會直接壞掉。
#
# This module deliberately owns its own user32 handle: argtypes/restype live on
# the function objects, so sharing one would leak these prototypes into other
# callers (`utils/window_capture/` passes its own RECT to GetWindowRect).
_user32 = ctypes.WinDLL("user32", use_last_error=True)

# HWND 是指標寬度的 handle。ctypes 預設把參數與回傳值當成 c_int，在 64 位元
# Windows 上會截斷成 32 位元——與 `OpenProcess` 那個經典陷阱同一類。每個函式
# 都明寫 argtypes/restype，不要依賴預設值。
#
# An HWND is a pointer-width handle. ctypes defaults to c_int, which truncates
# it to 32 bits on 64-bit Windows. Every prototype below is explicit.
EnumWindowsProc = WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND
_user32.CloseWindow.argtypes = [wintypes.HWND]
_user32.CloseWindow.restype = wintypes.BOOL
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.DestroyWindow.restype = wintypes.BOOL
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 wintypes.UINT]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, wintypes.BOOL]
_user32.MoveWindow.restype = wintypes.BOOL
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsIconic.restype = wintypes.BOOL

WM_CLOSE = 0x0010
SW_RESTORE = 9


def get_all_window_hwnd() -> List[Tuple[int, str]]:
    """
    列舉所有可見視窗，依 z-order（最前面的在最前）
    Enumerate all visible windows, front-most first

    hwnd 一律回傳 **int**。先前的回呼把 hwnd 宣告成 `POINTER(c_int)`，於是每個
    handle 都成了 `LP_c_long` 物件：`int(hwnd)` 會丟 `ValueError`，也沒辦法拿去
    跟其他 Win32 呼叫組合，等於這份清單只能看不能用。

    :return: [(hwnd, window_title), ...]
    """
    window_info: List[Tuple[int, str]] = []

    def _foreach_window(hwnd, _l_param) -> bool:
        if _user32.IsWindowVisible(hwnd):
            length = _user32.GetWindowTextLengthW(hwnd)
            buff = create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buff, length + 1)
            window_info.append((int(hwnd), buff.value))
        return True

    _user32.EnumWindows(EnumWindowsProc(_foreach_window), 0)
    return window_info


def get_one_window_hwnd(window_class: Optional[str],
                        window_name: Optional[str]) -> int:
    """
    取得指定視窗的 HWND
    Get window handle by class name and/or window title
    """
    return int(_user32.FindWindowW(window_class, window_name) or 0)


def get_foreground_window() -> int:
    """
    目前的前景視窗 HWND，沒有就回 0
    The foreground window's HWND, or 0 when there is none
    """
    return int(_user32.GetForegroundWindow() or 0)


def get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """
    視窗在螢幕座標上的矩形，查不到回 None
    The window's screen-coordinate rectangle, or None if unavailable

    :return: (left, top, right, bottom)
    """
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, byref(rect)):
        return None
    return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))


def is_window_minimized(hwnd: int) -> bool:
    """
    視窗目前是否被最小化
    Whether the window is currently minimized
    """
    return bool(_user32.IsIconic(hwnd))


def close_window(hwnd: int) -> bool:
    """
    請視窗關閉（送出 WM_CLOSE）
    Ask a window to close (posts WM_CLOSE)

    **行為變更**：本函式過去呼叫 Win32 的 `CloseWindow()`，而那支 API 其實是把
    視窗**最小化**，不是關閉——這是 Win32 有名的命名陷阱。舊行為已改名為
    :func:`minimize_window`。要關掉別的行程的視窗只能送 WM_CLOSE，
    `DestroyWindow` 無法銷毀不屬於本執行緒的視窗。
    """
    return bool(_user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))


def minimize_window(hwnd: int) -> bool:
    """
    最小化視窗
    Minimize a window

    包的是 Win32 `CloseWindow()`——名字寫 close，做的是 minimize。
    Wraps Win32 `CloseWindow()`, which minimizes despite its name.
    """
    return bool(_user32.CloseWindow(hwnd))


def destroy_window(hwnd: int) -> bool:
    """
    銷毀視窗（只對本執行緒自己的視窗有效）
    Destroy a window (only works on windows owned by this thread)
    """
    return bool(_user32.DestroyWindow(hwnd))


def set_foreground_window(hwnd: int) -> None:
    """
    設定視窗為前景視窗
    Set window to foreground
    """
    _user32.SetForegroundWindow(hwnd)


def set_window_position(hwnd: int, position: int) -> None:
    """
    設定視窗位置 (僅改變 Z-order，不改變大小與座標)
    Set window position (only Z-order, no resize or move)
    """
    swp_no_size = 0x0001
    swp_no_move = 0x0002
    _user32.SetWindowPos(hwnd, position, 0, 0, 0, 0,
                         swp_no_move | swp_no_size)


def show_window(hwnd: int, cmd_show: int) -> None:
    """
    顯示或隱藏視窗
    Show or hide a window

    :param cmd_show: Win32 ShowWindow flag (e.g., 0=Hide, 1=Normal, 2=Minimized, 3=Maximized)
    """
    if cmd_show < 0 or cmd_show > 11:  # Win32 ShowWindow 常見範圍
        cmd_show = 1  # 預設為 Normal
    _user32.ShowWindow(hwnd, cmd_show)
    # 隱藏之後不該再把它拉到前景，那是自相矛盾的一組動作。
    # Do not pull a window forward right after hiding it.
    if cmd_show != 0:
        _user32.SetForegroundWindow(hwnd)


def move_window(hwnd: int, x: int, y: int, width: int, height: int,
                repaint: bool = True) -> bool:
    """
    搬移與調整視窗大小 (一次設定座標與寬高)
    Move and resize a window in one call.
    """
    return bool(_user32.MoveWindow(int(hwnd), int(x), int(y),
                                   int(width), int(height),
                                   bool(repaint)))
