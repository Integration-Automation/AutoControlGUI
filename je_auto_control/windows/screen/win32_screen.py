import sys

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise Exception("should be only loaded on windows")

import ctypes

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


def size():
    return [user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)]
