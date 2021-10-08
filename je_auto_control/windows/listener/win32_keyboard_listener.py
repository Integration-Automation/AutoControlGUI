from ctypes import *
from ctypes.wintypes import MSG

user32 = windll.user32
kernel32 = windll.kernel32

wm_keydown = 0x100


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
        if w_param is not wm_keydown:
            return user32.CallNextHookEx(self.hooked, code, w_param, l_param)
            # int to hex
        temp = hex(l_param[0] & 0xFFFFFFFF)
        print("Hooked Key: " + temp)
        print(int(temp, 16))
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
    wh_keyboard_ll = 13
    win32_listener = Win32Listener(wh_keyboard_ll)
    win32_listener.start_listener()
