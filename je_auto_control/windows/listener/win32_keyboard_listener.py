import sys

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise Exception("should be only loaded on windows")

from ctypes import *
from ctypes.wintypes import MSG

from threading import Thread

from queue import Queue

user32 = windll.user32
kernel32 = windll.kernel32

wm_keydown = 0x100


class Win32KeyboardListener(Thread):

    def __init__(self):
        super().__init__()
        self.hooked = None
        self.record_queue = None
        self.record_flag = False
        self.hook_event_code_int = 13

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
        self.record_queue = None
        sys.exit(0)

    def _win32_hook_proc(self, code, w_param, l_param):
        if w_param is not wm_keydown:
            return user32.CallNextHookEx(self.hooked, code, w_param, l_param)
        if self.record_flag is True:
            # int to hex
            temp = hex(l_param[0] & 0xFFFFFFFF)
            self.record_queue.put(("keyboard", temp))
        return user32.CallNextHookEx(self.hooked, code, w_param, l_param)

    def _get_function_pointer(self, function):
        win_function = WINFUNCTYPE(c_int, c_int, c_int, POINTER(c_void_p))
        return win_function(function)

    def _start_listener(self):
        pointer = self._get_function_pointer(self._win32_hook_proc)
        if self._set_win32_hook(pointer):
            print("start listener")
        else:
            print("failed to start")
        message = MSG()
        user32.GetMessageA(byref(message), 0, 0, 0)

    def record(self, want_to_record_queue):
        self.record_flag = True
        self.record_queue = want_to_record_queue
        self.start()

    def stop_record(self):
        self.record_flag = False
        return self.record_queue

    def run(self):
        self._start_listener()


if __name__ == "__main__":
    win32_keyboard_listener = Win32KeyboardListener()
    record_queue = Queue()
    win32_keyboard_listener.record(record_queue)
    from time import sleep
    sleep(3)
    temp = win32_keyboard_listener.stop_record()
    for i in temp.queue:
        print(i)
