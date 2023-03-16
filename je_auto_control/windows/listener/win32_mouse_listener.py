import sys

from je_auto_control.utils.exception.exception_tags import windows_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error)

from ctypes import windll, WINFUNCTYPE, c_int, POINTER, c_void_p, byref
from ctypes.wintypes import MSG

from threading import Thread

from queue import Queue

from je_auto_control.windows.mouse.win32_ctype_mouse_control import position

_user32: windll.user32 = windll.user32
_kernel32: windll.kernel32 = windll.kernel32
# Left mouse button down 0x0201
# Right mouse button down 0x0204
# Middle mouse button down 0x0207
_wm_mouse_key_code: list = [0x0201, 0x0204, 0x0207]


def _get_function_pointer(function) -> WINFUNCTYPE:
    win_function = WINFUNCTYPE(c_int, c_int, c_int, POINTER(c_void_p))
    return win_function(function)


class Win32MouseListener(Thread):

    def __init__(self):
        super().__init__()
        self.setDaemon(True)
        self.hooked: [None, int] = None
        self.record_queue: [None, Queue] = None
        self.record_flag: bool = False
        self.hook_event_code_int: int = 14

    def _set_win32_hook(self, point) -> bool:
        self.hooked = _user32.SetWindowsHookExA(
            self.hook_event_code_int,
            point,
            0,
            0
        )
        if not self.hooked:
            return False
        return True

    def _remove_win32_hook_proc(self) -> None:
        if self.hooked is None:
            return
        _user32.UnhookWindowsHookEx(self.hooked)
        self.hooked = None

    def _win32_hook_proc(self, code, w_param, l_param) -> _user32.CallNextHookEx:
        if w_param not in _wm_mouse_key_code:
            return _user32.CallNextHookEx(self.hooked, code, w_param, l_param)
        if w_param == _wm_mouse_key_code[0] and self.record_flag is True:
            x, y = position()
            self.record_queue.put(("mouse_left", x, y))
        elif w_param == _wm_mouse_key_code[1] and self.record_flag is True:
            x, y = position()
            self.record_queue.put(("mouse_right", x, y))
        elif w_param == _wm_mouse_key_code[2] and self.record_flag is True:
            x, y = position()
            self.record_queue.put(("mouse_middle", x, y))
        return _user32.CallNextHookEx(self.hooked, code, w_param, l_param)

    def _start_listener(self) -> None:
        pointer = _get_function_pointer(self._win32_hook_proc)
        self._set_win32_hook(pointer)
        message = MSG()
        _user32.GetMessageA(byref(message), 0, 0, 0)

    def record(self, want_to_record_queue) -> None:
        self.record_flag = True
        self.record_queue = want_to_record_queue
        self.start()

    def stop_record(self) -> Queue:
        self.record_flag = False
        self._remove_win32_hook_proc()
        return self.record_queue

    def run(self) -> None:
        self._start_listener()
