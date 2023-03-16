import sys

from je_auto_control.utils.exception.exception_tags import windows_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error)

import ctypes
from ctypes import wintypes
from je_auto_control.windows.core.utils.win32_vk import win32_EventF_UNICODE, win32_VkToVSC

user32 = ctypes.WinDLL('user32', use_last_error=True)

wintypes.ULONG_PTR = wintypes.WPARAM

Mouse: int = 0
Keyboard: int = 1
Hardware: int = 2


class MouseInput(ctypes.Structure):
    _fields_: tuple = (("dx", wintypes.LONG),
                       ("dy", wintypes.LONG),
                       ("mouseData", wintypes.DWORD),
                       ("dwFlags", wintypes.DWORD),
                       ("time", wintypes.DWORD),
                       ("dwExtraInfo", ctypes.c_void_p))


class KeyboardInput(ctypes.Structure):
    _fields_: tuple = (("wVk", wintypes.WORD),
                       ("wScan", wintypes.WORD),
                       ("dwFlags", wintypes.DWORD),
                       ("time", wintypes.DWORD),
                       ("dwExtraInfo", ctypes.c_void_p))

    def __init__(self, *args, **kwds):
        super(KeyboardInput, self).__init__(*args, **kwds)
        if not self.dwFlags & win32_EventF_UNICODE:
            self.wScan = user32.MapVirtualKeyExW(self.wVk, win32_VkToVSC, 0)


class HardwareInput(ctypes.Structure):
    _fields_: tuple = (("uMsg", wintypes.DWORD),
                       ("wParamL", wintypes.WORD),
                       ("wParamH", wintypes.WORD))


class Input(ctypes.Structure):
    class INPUTUnion(ctypes.Union):
        _fields_: tuple = (("ki", KeyboardInput),
                           ("mi", MouseInput),
                           ("hi", HardwareInput))

    _anonymous_: tuple = ("_input",)
    _fields_: tuple = (("type", wintypes.DWORD),
                       ("_input", INPUTUnion))


def _check_count(result, func, args) -> list:
    if result == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    return args


LPINPUT: ctypes.POINTER = ctypes.POINTER(Input)

SendInput: user32.SendInput = user32.SendInput

user32.SendInput.errcheck = _check_count
user32.SendInput.arg_types = (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
