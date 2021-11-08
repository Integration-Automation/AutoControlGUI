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

_get_cursor_pos = windll.user32.GetCursorPos
_set_cursor_pos = windll.user32.SetCursorPos


def mouse_event(event, x: int, y: int, dwData: int = 0):
    """
    :param event which event we use
    :param x event x
    :param y event y
    :param dwData still 0
    """
    width, height = size()
    convertedX = 65536 * x // width + 1
    convertedY = 65536 * y // height + 1
    ctypes.windll.user32.mouse_event(event, ctypes.c_long(convertedX), ctypes.c_long(convertedY), dwData, 0)


def position():
    """
    get mouse position
    """
    point = wintypes.POINT()
    if _get_cursor_pos(ctypes.byref(point)):
        return point.x, point.y
    else:
        return None


def set_position(x: int, y: int):
    """
    :param x set mouse position x
    :param y set mouse position y
    """
    pos = x, y
    _set_cursor_pos(*pos)


def press_mouse(press_button: int):
    """
    :param press_button which button we want to press
    """
    SendInput(1, ctypes.byref(
        Input(type=Mouse, _input=Input.INPUT_Union(
            mi=MouseInput(dwFlags=press_button[1], mouseData=press_button[2])))),
              ctypes.sizeof(Input))


def release_mouse(release_button: int):
    """
    :param release_button which button we want to release
    """
    SendInput(1, ctypes.byref(
        Input(type=Mouse, _input=Input.INPUT_Union(
            mi=MouseInput(dwFlags=release_button[0], mouseData=release_button[2])))),
              ctypes.sizeof(Input))


def click_mouse(mouse_keycode: int, x: int = None, y: int = None):
    """
    :param mouse_keycode which mouse keycode we want to click
    :param x mouse x position
    :param y mouse y position
    """
    if x and y is not None:
        set_position(x, y)
    press_mouse(mouse_keycode)
    release_mouse(mouse_keycode)


def scroll(scroll_value: int, x: int = None, y: int = None):
    """
    :param scroll_value scroll count
    :param x scroll x
    :param y scroll y
    """
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
