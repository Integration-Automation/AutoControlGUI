import sys

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise Exception("should be only loaded on windows")

import ctypes


def check_key_is_press(keycode):
    if type(keycode) is int:
        temp = ctypes.windll.user32.GetKeyState(keycode)
    else:
        temp = ctypes.windll.user32.GetKeyState(ord(keycode))
    if temp > 1:
        return True
