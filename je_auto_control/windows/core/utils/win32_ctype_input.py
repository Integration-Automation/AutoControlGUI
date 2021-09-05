import sys

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise Exception("should be only loaded on windows")

import ctypes
from ctypes import wintypes
from ctypes import windll
from je_auto_control.windows.core.utils.win32_vk import *

user32 = ctypes.WinDLL('user32', use_last_error=True)

wintypes.ULONG_PTR = wintypes.WPARAM

Mouse = 0
Keyboard = 1
Hardware = 2


class MouseInput(ctypes.Structure):
    _fields_ = (("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p))


class KeyboardInput(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p))

    def __init__(self, *args, **kwds):
        super(KeyboardInput, self).__init__(*args, **kwds)
        if not self.dwFlags & win32_EventF_UNICODE:
            self.wScan = user32.MapVirtualKeyExW(self.wVk, win32_VkToVSC, 0)


class HardwareInput(ctypes.Structure):
    _fields_ = (("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD))


class Input(ctypes.Structure):
    class INPUT_Union(ctypes.Union):
        _fields_ = (("ki", KeyboardInput),
                    ("mi", MouseInput),
                    ("hi", HardwareInput))

    _anonymous_ = ("_input",)
    _fields_ = (("type", wintypes.DWORD),
                ("_input", INPUT_Union))


LPINPUT = ctypes.POINTER(Input)


def _check_count(result, func, args):
    if result == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    return args


SendInput = user32.SendInput

user32.SendInput.errcheck = _check_count
user32.SendInput.arg_types = (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
