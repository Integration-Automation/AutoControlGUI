import sys

from je_auto_control.utils.exception.exception_tags import windows_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# 僅允許在 Windows 平台使用 Only allow on Windows platform
if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

from je_auto_control.windows.core.utils.win32_ctype_input import Input, user32
from je_auto_control.windows.core.utils.win32_ctype_input import Keyboard
from je_auto_control.windows.core.utils.win32_ctype_input import KeyboardInput
from je_auto_control.windows.core.utils.win32_ctype_input import SendInput
from je_auto_control.windows.core.utils.win32_ctype_input import ctypes
from je_auto_control.windows.core.utils.win32_vk import WIN32_EventF_KEYUP


def press_key(keycode: int) -> None:
    """
    模擬按下鍵盤按鍵
    Simulate pressing a key

    :param keycode: 鍵盤虛擬鍵碼 Virtual key code
    """
    keyboard = Input(type=Keyboard, ki=KeyboardInput(wVk=keycode))
    SendInput(1, ctypes.byref(keyboard), ctypes.sizeof(keyboard))


def release_key(keycode: int) -> None:
    """
    模擬放開鍵盤按鍵
    Simulate releasing a key

    :param keycode: 鍵盤虛擬鍵碼 Virtual key code
    """
    keyboard = Input(type=Keyboard, ki=KeyboardInput(wVk=keycode, dwFlags=WIN32_EventF_KEYUP))
    SendInput(1, ctypes.byref(keyboard), ctypes.sizeof(keyboard))


def send_key_event_to_window(window: str, keycode: int) -> None:
    """
    將鍵盤事件送到指定視窗
    Send key event to a specific window

    :param window: 視窗標題 Window title
    :param keycode: 鍵盤虛擬鍵碼 Virtual key code
    """
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    hwnd = user32.FindWindowW(None, window)
    if hwnd:
        user32.PostMessageW(hwnd, WM_KEYDOWN, keycode, 0)
        user32.PostMessageW(hwnd, WM_KEYUP, keycode, 0)
    else:
        raise AutoControlException(f"Window '{window}' not found")