import sys

from je_auto_control.utils.je_auto_control_exception.exception_tag import windows_import_error
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error)

import ctypes

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


def size():
    """
    get screen size
    """
    return [user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)]
