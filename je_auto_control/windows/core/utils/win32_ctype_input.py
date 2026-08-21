import sys

from je_auto_control.utils.exception.exception_tags import windows_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

import ctypes
from ctypes import wintypes
from je_auto_control.windows.core.utils.win32_vk import WIN32_EventF_UNICODE, WIN32_VkToVSC

user32 = ctypes.WinDLL('user32', use_last_error=True)

Mouse: int = 0
Keyboard: int = 1
Hardware: int = 2


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
        if not self.dwFlags & WIN32_EventF_UNICODE:
            self.wScan = user32.MapVirtualKeyExW(self.wVk, WIN32_VkToVSC, 0)


class HardwareInput(ctypes.Structure):
    _fields_ = (("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD))


class Input(ctypes.Structure):
    class INPUTUnion(ctypes.Union):
        _fields_ = (("ki", KeyboardInput),
                    ("mi", MouseInput),
                    ("hi", HardwareInput))

    _anonymous_ = ("_input",)
    _fields_ = (("type", wintypes.DWORD),
                ("_input", INPUTUnion))


def _check_count(result, func, args) -> list:
    if result == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    return args


LPINPUT = ctypes.POINTER(Input)

SendInput = user32.SendInput

# 回傳 args 原封不動是 ctypes 對 errcheck 的既定約定，而 typeshed 把這個
# hook 標成回傳單一 _CData——任何 pass-through 的 errcheck 都滿足不了。
# reason: returning args unchanged is ctypes' documented errcheck contract.
user32.SendInput.errcheck = _check_count  # type: ignore[assignment]
user32.SendInput.argtypes = (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
