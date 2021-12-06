import sys

from je_auto_control.utils.exception.exception_tag import windows_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error)

from ctypes import *
from ctypes.wintypes import MSG

from threading import Thread

from queue import Queue

from je_auto_control.windows.mouse.win32_ctype_mouse_control import position

user32 = windll.user32
kernel32 = windll.kernel32
"""
Left mouse button down 0x0201
Right mouse button down 0x0204
Middle mouse button down 0x0207
"""
wm_mouse_key_code = [0x0201, 0x0204, 0x0207]


class Win32MouseListener(Thread):

    def __init__(self):
        super().__init__()
        self.setDaemon(True)
        self.hooked = None
        self.record_queue = None
        self.record_flag = False
        self.hook_event_code_int = 14

    def _set_win32_hook(self, point):
        self.hooked = user32.SetWindowsHookExA(
            self.hook_event_code_int,
            point,
            0,
            0
        )
        if not self.hooked:
            return False
        return True

    def _remove_win32_hook_proc(self):
        if self.hooked is None:
            return
        user32.UnhookWindowsHookEx(self.hooked)
        self.hooked = None

    def _win32_hook_proc(self, code, w_param, l_param):
        if w_param not in wm_mouse_key_code:
            return user32.CallNextHookEx(self.hooked, code, w_param, l_param)
        if w_param == wm_mouse_key_code[0] and self.record_flag is True:
            x, y = position()
            self.record_queue.put(("mouse_left", x, y))
        elif w_param == wm_mouse_key_code[1] and self.record_flag is True:
            x, y = position()
            self.record_queue.put(("mouse_right", x, y))
        elif w_param == wm_mouse_key_code[2] and self.record_flag is True:
            x, y = position()
            self.record_queue.put(("mouse_middle", x, y))
        return user32.CallNextHookEx(self.hooked, code, w_param, l_param)

    def _get_function_pointer(self, function):
        win_function = WINFUNCTYPE(c_int, c_int, c_int, POINTER(c_void_p))
        return win_function(function)

    def _start_listener(self):
        pointer = self._get_function_pointer(self._win32_hook_proc)
        self._set_win32_hook(pointer)
        message = MSG()
        user32.GetMessageA(byref(message), 0, 0, 0)

    def record(self, want_to_record_queue):
        self.record_flag = True
        self.record_queue = want_to_record_queue
        self.start()

    def stop_record(self):
        self.record_flag = False
        self._remove_win32_hook_proc()
        return self.record_queue

    def run(self):
        self._start_listener()


if __name__ == "__main__":
    win32_mouse_listener = Win32MouseListener()
    record_queue = Queue()
    win32_mouse_listener.record(record_queue)
    from time import sleep
    sleep(3)
    temp = win32_mouse_listener.stop_record()
    for i in temp.queue:
        print(i)


