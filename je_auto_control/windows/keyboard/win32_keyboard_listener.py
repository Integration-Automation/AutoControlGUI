import ctypes
import sys

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise Exception("should be only loaded on windows")


def check_key_is_press(key_code):
    if type(key_code) is int:
        temp = ctypes.windll.user32.GetKeyState(key_code)
    else:
        temp = ctypes.windll.user32.GetKeyState(ord(key_code))
    if temp > 1:
        return True
