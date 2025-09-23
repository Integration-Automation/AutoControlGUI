from ctypes import WINFUNCTYPE, c_bool, c_int, POINTER, create_unicode_buffer
from typing import Union

from je_auto_control.windows.core.utils.win32_ctype_input import user32

EnumWindows = user32.EnumWindows
EnumWindowsProc = WINFUNCTYPE(c_bool, POINTER(c_int), POINTER(c_int))
GetWindowText = user32.GetWindowTextW
GetWindowTextLength = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible
FindWindowW = user32.FindWindowW
CloseWindow = user32.CloseWindow
DestroyWindow = user32.DestroyWindow


def get_all_window_hwnd():
    window_info = []

    def _foreach_window(hwnd, l_param):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            buff = create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            window_info.append((hwnd, buff.value))
        return True

    EnumWindows(EnumWindowsProc(_foreach_window), 0)
    return window_info


def get_one_window_hwnd(window_class: Union[None, str], window_name: Union[None, str]):
    return FindWindowW(window_class, window_name)


def close_window(hwnd) -> bool:
    return CloseWindow(hwnd)


def destroy_window(hwnd) -> bool:
    return DestroyWindow(hwnd)


def set_foreground_window(hwnd) -> None:
    user32.SetForegroundWindow(hwnd)

def set_window_positon(hwnd, position: int) -> None:
    swp_no_size = 0x0001
    swp_no_move = 0x0002
    user32.SetWindowPos(hwnd, position, 0, 0, 0, 0, swp_no_move | swp_no_size)