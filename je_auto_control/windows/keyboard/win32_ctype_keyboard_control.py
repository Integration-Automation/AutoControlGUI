import sys

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise Exception("should be only loaded on windows")

from je_auto_control.windows.core.utils.win32_ctype_input import Input
from je_auto_control.windows.core.utils.win32_ctype_input import Keyboard
from je_auto_control.windows.core.utils.win32_ctype_input import KeyboardInput
from je_auto_control.windows.core.utils.win32_ctype_input import SendInput
from je_auto_control.windows.core.utils.win32_ctype_input import ctypes
from je_auto_control.windows.core.utils.win32_ctype_input import win32_EventF_KEYUP


def press_key(keycode):
    x = Input(type=Keyboard, ki=KeyboardInput(wVk=keycode))
    SendInput(1, ctypes.byref(x), ctypes.sizeof(x))


def release_key(keycode):
    x = Input(type=Keyboard, ki=KeyboardInput(wVk=keycode, dwFlags=win32_EventF_KEYUP))
    SendInput(1, ctypes.byref(x), ctypes.sizeof(x))
