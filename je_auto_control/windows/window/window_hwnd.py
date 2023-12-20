from ctypes import WINFUNCTYPE, c_bool, c_int, POINTER, create_unicode_buffer
from typing import Union

from je_auto_control.windows.core.utils.win32_ctype_input import user32
from je_auto_control.windows.keyboard.win32_ctype_keyboard_control import press_key

EnumWindows = user32.EnumWindows
EnumWindowsProc = WINFUNCTYPE(c_bool, POINTER(c_int), POINTER(c_int))
GetWindowText = user32.GetWindowTextW
GetWindowTextLength = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible
FindWindowW = user32.FindWindowW
PostMessageW = user32.PostMessageW
SendMessageW = user32.SendMessageW


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


def send_key_to_window(window_name: str, action_message: int,
                       key_code_1: int, key_code_2: int):
    _hwnd = FindWindowW(window_name)
    post_status = SendMessageW(_hwnd, action_message, key_code_1, key_code_2)
    return _hwnd, post_status


def post_key_to_window(window_name: str, action_message: int,
                       key_code_1: int, key_code_2: int):
    _hwnd = FindWindowW(window_name)
    post_status = PostMessageW(_hwnd, action_message, key_code_1, key_code_2)
    return _hwnd, post_status
