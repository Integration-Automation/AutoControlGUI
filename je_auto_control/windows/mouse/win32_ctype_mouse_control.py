import sys

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise Exception("should be only loaded on windows")

from je_auto_control.windows.core.utils.win32_ctype_input import Input
from je_auto_control.windows.core.utils.win32_ctype_input import win32_LEFTDOWN
from je_auto_control.windows.core.utils.win32_ctype_input import win32_LEFTUP
from je_auto_control.windows.core.utils.win32_ctype_input import win32_MIDDLEDOWN
from je_auto_control.windows.core.utils.win32_ctype_input import win32_MIDDLEUP
from je_auto_control.windows.core.utils.win32_ctype_input import Mouse
from je_auto_control.windows.core.utils.win32_ctype_input import MouseInput
from je_auto_control.windows.core.utils.win32_ctype_input import win32_RIGHTDOWN
from je_auto_control.windows.core.utils.win32_ctype_input import win32_RIGHTUP
from je_auto_control.windows.core.utils.win32_ctype_input import SendInput
from je_auto_control.windows.core.utils.win32_ctype_input import win32_XBUTTON1
from je_auto_control.windows.core.utils.win32_ctype_input import win32_XBUTTON2
from je_auto_control.windows.core.utils.win32_ctype_input import win32_DOWN
from je_auto_control.windows.core.utils.win32_ctype_input import win32_XUP
from je_auto_control.windows.core.utils.win32_ctype_input import windll
from je_auto_control.windows.core.utils.win32_ctype_input import wintypes
from je_auto_control.windows.core.utils.win32_vk import win32_WHEEL
from je_auto_control.windows.core.utils.win32_ctype_input import ctypes
from je_auto_control.windows.screen import size

win32_mouse_left = (win32_LEFTUP, win32_LEFTDOWN, 0)
win32_mouse_middle = (win32_MIDDLEUP, win32_MIDDLEDOWN, 0)
win32_mouse_right = (win32_RIGHTUP, win32_RIGHTDOWN, 0)
win32_mouse_x1 = (win32_XUP, win32_DOWN, win32_XBUTTON1)
win32_mouse_x2 = (win32_XUP, win32_DOWN, win32_XBUTTON2)

get_cursor_pos = windll.user32.GetCursorPos
set_cursor_pos = windll.user32.SetCursorPos


def mouse_event(event, x, y, dwData=0):
    width, height = size()
    convertedX = 65536 * x // width + 1
    convertedY = 65536 * y // height + 1
    ctypes.windll.user32.mouse_event(event, ctypes.c_long(convertedX), ctypes.c_long(convertedY), dwData, 0)


def position():
    point = wintypes.POINT()
    if get_cursor_pos(ctypes.byref(point)):
        return point.x, point.y
    else:
        return None


def set_position(x, y):
    pos = x, y
    set_cursor_pos(*pos)


def press_mouse(press_button):
    SendInput(1, ctypes.byref(
        Input(type=Mouse, _input=Input.INPUT_Union(
            mi=MouseInput(dwFlags=press_button[1], mouseData=press_button[2])))),
              ctypes.sizeof(Input))


def release_mouse(release_button):
    SendInput(1, ctypes.byref(
        Input(type=Mouse, _input=Input.INPUT_Union(
            mi=MouseInput(dwFlags=release_button[0], mouseData=release_button[2])))),
              ctypes.sizeof(Input))


def click_mouse(mouse_keycode):
    press_mouse(mouse_keycode)
    release_mouse(mouse_keycode)


def scroll(scroll_value, x=None, y=None):
    now_cursor_x, now_cursor_y = position()
    width, height = size()
    if x is None:
        x = now_cursor_x
    else:
        if x < 0:
            x = 0
        elif x >= width:
            x = width - 1
    if y is None:
        y = now_cursor_y
    else:
        if y < 0:
            y = 0
        elif y >= height:
            y = height - 1
    mouse_event(win32_WHEEL, x, y, dwData=scroll_value)
