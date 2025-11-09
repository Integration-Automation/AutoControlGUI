import sys
from ctypes import windll, WINFUNCTYPE, c_int, POINTER, c_void_p, byref
from ctypes.wintypes import MSG
from threading import Thread
from queue import Queue
from typing import Optional

from je_auto_control.utils.exception.exception_tags import windows_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# 僅允許在 Windows 平台使用 Only allow on Windows platform
if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

_user32 = windll.user32
_kernel32 = windll.kernel32
_wm_keydown: int = 0x100


def _get_function_pointer(function) -> WINFUNCTYPE:
    """
    將 Python 函式轉換成 Win32 API 可用的函式指標
    Convert Python function to Win32-compatible function pointer
    """
    win_function = WINFUNCTYPE(c_int, c_int, c_int, POINTER(c_void_p))
    return win_function(function)


class Win32KeyboardListener(Thread):
    """
    Win32KeyboardListener
    Windows 鍵盤事件監聽器
    - 使用 SetWindowsHookExA 設置鍵盤 hook
    - 將鍵盤事件記錄到 Queue
    """

    def __init__(self):
        super().__init__()
        self.daemon = True
        self.hooked: Optional[int] = None
        self.record_queue: Optional[Queue] = None
        self.record_flag: bool = False
        self.hook_event_code_int: int = 13  # WH_KEYBOARD_LL

    def _set_win32_hook(self, point) -> bool:
        """
        設置鍵盤 hook
        Set keyboard hook
        """
        self.hooked = _user32.SetWindowsHookExA(
            self.hook_event_code_int,
            point,
            0,
            0
        )
        return bool(self.hooked)

    def _remove_win32_hook_proc(self) -> None:
        """
        移除鍵盤 hook
        Remove keyboard hook
        """
        if self.hooked:
            _user32.UnhookWindowsHookEx(self.hooked)
            self.hooked = None

    def _win32_hook_proc(self, code, w_param, l_param):
        """
        鍵盤事件處理函式
        Keyboard hook procedure
        """
        if w_param != _wm_keydown:
            return _user32.CallNextHookEx(self.hooked, code, w_param, l_param)

        if self.record_flag and self.record_queue is not None:
            # 將 l_param 轉換成 keycode
            temp = hex(l_param[0] & 0xFFFFFFFF)
            self.record_queue.put(("AC_type_keyboard", int(temp, 16)))

        return _user32.CallNextHookEx(self.hooked, code, w_param, l_param)

    def _start_listener(self) -> None:
        """
        啟動鍵盤監聽
        Start keyboard listener
        """
        pointer = _get_function_pointer(self._win32_hook_proc)
        if not self._set_win32_hook(pointer):
            raise AutoControlException("Failed to set keyboard hook")

        message = MSG()
        # 進入訊息迴圈 Enter message loop
        _user32.GetMessageA(byref(message), 0, 0, 0)

    def record(self, want_to_record_queue: Queue) -> None:
        """
        開始紀錄鍵盤事件
        Start recording keyboard events
        """
        self.record_flag = True
        self.record_queue = want_to_record_queue
        self.start()

    def stop_record(self) -> Queue:
        """
        停止紀錄並移除 hook
        Stop recording and remove hook
        """
        self.record_flag = False
        self._remove_win32_hook_proc()
        return self.record_queue

    def run(self) -> None:
        """
        Thread 執行入口
        Thread run entry
        """
        self._start_listener()