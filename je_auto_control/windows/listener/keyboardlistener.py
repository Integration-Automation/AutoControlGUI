from ctypes import *
from ctypes.wintypes import MSG

user32 = windll.user32
kernel32 = windll.kernel32

wh_keyboard_ll = 13
wm_keydown = 0x0100


class KeyBoardListener:

    def __init__(self):
        self.hooked = None

    def set_keyboard_hook(self, pointer):
        self.hooked = user32.SetWindowsHookExA(
            wh_keyboard_ll,
            pointer,
            0,
            0
        )
        if not self.hooked:
            return False
        return True

    def remove_keyboard_hook_proc(self):
        if self.hooked is None:
            return
        user32.UnhookWindowsHookEx(self.hooked)
        self.hooked = None


def get_function_pointer(function):
    win_function = WINFUNCTYPE(c_int, c_int, c_int, POINTER(c_void_p))
    return win_function(function)


def keyboard_hook_proc(code, w_param, l_param):
    if w_param is not wm_keydown:
        return user32.CallNextHookEx(keyboard_listener.hooked, code, w_param, l_param)
    # int to hex
    temp = hex(l_param[0] & 0xFFFFFFFF)
    # print("Hooked Key: " + temp)
    # print(int(temp, 16))
    return user32.CallNextHookEx(keyboard_listener.hooked, code, w_param, l_param)


def start_listener():
    message = MSG()
    user32.GetMessageA(byref(message), 0, 0, 0)


keyboard_listener = KeyBoardListener()
pointer = get_function_pointer(keyboard_hook_proc)
if keyboard_listener.set_keyboard_hook(pointer):
    print("start hook keyboard")

start_listener()
