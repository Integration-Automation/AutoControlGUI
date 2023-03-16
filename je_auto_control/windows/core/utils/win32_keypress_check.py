import sys

from je_auto_control.utils.exception.exception_tags import windows_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error)

import ctypes


def check_key_is_press(keycode: [int, str]) -> bool:
    if isinstance(keycode, int):
        temp: int = ctypes.windll.user32.GetKeyState(keycode)
    else:
        temp = ctypes.windll.user32.GetKeyState(ord(keycode))
    if temp > 1:
        return True
    return False
