from ctypes import *
from ctypes.wintypes import MSG

from je_auto_control.windows.mouse.win32_ctype_mouse_control import position

user32 = windll.user32
kernel32 = windll.kernel32

wm_mouse_key_code = [0x0201, 0x0204]


class Win32Listener:

    def __init__(self, hook_event_code_int):
        self.hooked = None
        self.hook_event_code_int = hook_event_code_int

    def set_win32_hook(self, point):
        self.hooked = user32.SetWindowsHookExA(
            self.hook_event_code_int,
            point,
            0,
            0
        )
        if not self.hooked:
            return False
        return True

    def remove_win32_hook_proc(self):
        if self.hooked is None:
            return
        user32.UnhookWindowsHookEx(self.hooked)
        self.hooked = None

    def win32_hook_proc(self, code, w_param, l_param):
        if w_param not in wm_mouse_key_code:
            return user32.CallNextHookEx(self.hooked, code, w_param, l_param)
        print(position())
        return user32.CallNextHookEx(self.hooked, code, w_param, l_param)

    def get_function_pointer(self, function):
        win_function = WINFUNCTYPE(c_int, c_int, c_int, POINTER(c_void_p))
        return win_function(function)

    def start_listener(self):
        pointer = self.get_function_pointer(self.win32_hook_proc)
        if self.set_win32_hook(pointer):
            print("start listener")
        else:
            print("failed to start")
        message = MSG()
        user32.GetMessageA(byref(message), 0, 0, 0)


if __name__ == "__main__":
    wh_mouse_ll = 14
    win32_listener = Win32Listener(wh_mouse_ll)
    win32_listener.start_listener()
