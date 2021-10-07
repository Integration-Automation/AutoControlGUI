import sys

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise Exception("should be only loaded on windows")

import ctypes
from ctypes.wintypes import MSG
from ctypes.wintypes import DWORD
from ctypes import *

from je_auto_control.windows.core.utils.win32_vk import win32_VK_RETURN
from je_auto_control.windows.core.utils.win32_vk import win32_VK_SHIFT
from je_auto_control.windows.core.utils.win32_vk import win32_VK_Menu

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

hc_action = 0
wh_keyboard_ll = 13
wh_keyboard = 2
wm_keydown = 0X0100

hook = None


class KeyboardHookStruct(Structure):
    _fields = [
        ('vk_code', DWORD),
        ('scan_code', DWORD),
        ('flags', DWORD),
        ('time', DWORD),
        ('dw_extra_info', POINTER(c_void_p))
    ]


functype_hook_proc = WINFUNCTYPE(ctypes.wintypes.LPVOID, c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)


def keyboard_hook_proc(code, w_param, l_param):
    if code == hc_action and w_param == wm_keydown:
        keyboard_struct = KeyboardHookStruct.from_address(l_param)
        # print(keyboard_struct._fields)
        user32.GetKeyState(win32_VK_SHIFT)
        user32.GetKeyState(win32_VK_Menu)
        state = (ctypes.c_char * 256)()
        user32.GetKeyboardState(byref(state))
        str = create_unicode_buffer(8)
        n = user32.ToUnicode(keyboard_struct._fields[0][0], keyboard_struct._fields[1][0], state, str, 8 - 1, 0)
        if n > 0:
            if keyboard_struct.vk_code == win32_VK_RETURN:
                print()
            else:
                print(ctypes.wstring_at(str), end="", flush=True)
    l_param = c_uint64(l_param)
    return user32.CallNextHookEx(hook, code, w_param, l_param)


def set_hook_proc(hook_pointer):
    hook = user32.SetWindowsHookExA(wh_keyboard_ll, hook_pointer, 0, 0)
    if not hook:
        return False
    return True


def remove_hook_proc():
    if hook is None:
        return
    user32.UnhookWindowsHookEx(hook)
    hook = None


pointer = functype_hook_proc(keyboard_hook_proc)
print(set_hook_proc(pointer))
msg = ctypes.wintypes.MSG()
while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
    user32.TranslateMessage(msg)
    user32.DispatchMessageW(msg)
