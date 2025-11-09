from ctypes import WINFUNCTYPE, c_bool, c_int, POINTER, create_unicode_buffer
from typing import Union, List, Tuple, Optional

from je_auto_control.windows.core.utils.win32_ctype_input import user32

# Win32 API 函式指標 Win32 API function pointers
EnumWindows = user32.EnumWindows
EnumWindowsProc = WINFUNCTYPE(c_bool, POINTER(c_int), POINTER(c_int))
GetWindowText = user32.GetWindowTextW
GetWindowTextLength = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible
FindWindowW = user32.FindWindowW
CloseWindow = user32.CloseWindow
DestroyWindow = user32.DestroyWindow


def get_all_window_hwnd() -> List[Tuple[int, str]]:
    """
    列舉所有可見視窗
    Enumerate all visible windows

    :return: [(hwnd, window_title), ...]
    """
    window_info: List[Tuple[int, str]] = []

    def _foreach_window(hwnd: int, l_param: int) -> bool:
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            buff = create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            window_info.append((hwnd, buff.value))
        return True

    EnumWindows(EnumWindowsProc(_foreach_window), 0)
    return window_info


def get_one_window_hwnd(window_class: Optional[str], window_name: Optional[str]) -> int:
    """
    取得指定視窗的 HWND
    Get window handle by class name and/or window title
    """
    return FindWindowW(window_class, window_name)


def close_window(hwnd: int) -> bool:
    """
    嘗試關閉視窗 (最小化)
    Attempt to close (minimize) a window
    """
    return bool(CloseWindow(hwnd))


def destroy_window(hwnd: int) -> bool:
    """
    銷毀視窗
    Destroy a window
    """
    return bool(DestroyWindow(hwnd))


def set_foreground_window(hwnd: int) -> None:
    """
    設定視窗為前景視窗
    Set window to foreground
    """
    user32.SetForegroundWindow(hwnd)


def set_window_position(hwnd: int, position: int) -> None:
    """
    設定視窗位置 (僅改變 Z-order，不改變大小與座標)
    Set window position (only Z-order, no resize or move)
    """
    SWP_NO_SIZE = 0x0001
    SWP_NO_MOVE = 0x0002
    user32.SetWindowPos(hwnd, position, 0, 0, 0, 0, SWP_NO_MOVE | SWP_NO_SIZE)


def show_window(hwnd: int, cmd_show: int) -> None:
    """
    顯示或隱藏視窗
    Show or hide a window

    :param cmd_show: Win32 ShowWindow flag (e.g., 0=Hide, 1=Normal, 2=Minimized, 3=Maximized)
    """
    if cmd_show < 0 or cmd_show > 11:  # Win32 ShowWindow 常見範圍
        cmd_show = 1  # 預設為 Normal
    user32.ShowWindow(hwnd, cmd_show)
    user32.SetForegroundWindow(hwnd)