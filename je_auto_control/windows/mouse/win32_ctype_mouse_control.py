import sys
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import windows_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error)

from je_auto_control.windows.core.utils.win32_ctype_input import Input, user32
from je_auto_control.windows.core.utils.win32_vk import WIN32_LEFTDOWN
from je_auto_control.windows.core.utils.win32_vk import WIN32_LEFTUP
from je_auto_control.windows.core.utils.win32_vk import WIN32_MIDDLEDOWN
from je_auto_control.windows.core.utils.win32_vk import WIN32_MIDDLEUP
from je_auto_control.windows.core.utils.win32_ctype_input import Mouse
from je_auto_control.windows.core.utils.win32_ctype_input import MouseInput
from je_auto_control.windows.core.utils.win32_vk import WIN32_RIGHTDOWN
from je_auto_control.windows.core.utils.win32_vk import WIN32_RIGHTUP
from je_auto_control.windows.core.utils.win32_ctype_input import SendInput
from je_auto_control.windows.core.utils.win32_vk import WIN32_XBUTTON1
from je_auto_control.windows.core.utils.win32_vk import WIN32_XBUTTON2
from je_auto_control.windows.core.utils.win32_vk import WIN32_DOWN
from je_auto_control.windows.core.utils.win32_vk import WIN32_XUP
from ctypes import windll
from je_auto_control.windows.core.utils.win32_ctype_input import wintypes
from je_auto_control.windows.core.utils.win32_vk import WIN32_WHEEL
from je_auto_control.windows.core.utils.win32_ctype_input import ctypes
from je_auto_control.windows.screen.win32_screen import size

win32_mouse_left: Tuple = (WIN32_LEFTUP, WIN32_LEFTDOWN, 0)
win32_mouse_middle: Tuple = (WIN32_MIDDLEUP, WIN32_MIDDLEDOWN, 0)
win32_mouse_right: Tuple = (WIN32_RIGHTUP, WIN32_RIGHTDOWN, 0)
win32_mouse_x1: Tuple = (WIN32_XUP, WIN32_DOWN, WIN32_XBUTTON1)
win32_mouse_x2: Tuple = (WIN32_XUP, WIN32_DOWN, WIN32_XBUTTON2)

_get_cursor_pos: windll.user32.GetCursorPos = windll.user32.GetCursorPos
_set_cursor_pos: windll.user32.SetCursorPos = windll.user32.SetCursorPos


def mouse_event(event, x: int, y: int, dwData: int = 0) -> None:
    """
    :param event which event we use
    :param x event x
    :param y event y
    :param dwData still 0
    """
    width, height = size()
    converted_x = 65536 * x // width + 1
    converted_y = 65536 * y // height + 1
    ctypes.windll.user32.mouse_event(event, ctypes.c_long(converted_x), ctypes.c_long(converted_y), dwData, 0)


def position() -> tuple[int, int] | None:
    """
    get mouse position
    """
    point = wintypes.POINT()
    if _get_cursor_pos(ctypes.byref(point)):
        return point.x, point.y
    else:
        return None


def set_position(x: int, y: int) -> None:
    """
    :param x set mouse position x
    :param y set mouse position y
    """
    pos = x, y
    _set_cursor_pos(*pos)


def press_mouse(press_button: int) -> None:
    """
    :param press_button which button we want to press
    """
    SendInput(1, ctypes.byref(
        Input(type=Mouse, _input=Input.INPUTUnion(
            mi=MouseInput(dwFlags=press_button[1], mouseData=press_button[2])))),
              ctypes.sizeof(Input))


def release_mouse(release_button: int) -> None:
    """
    :param release_button which button we want to release
    """
    SendInput(1, ctypes.byref(
        Input(type=Mouse, _input=Input.INPUTUnion(
            mi=MouseInput(dwFlags=release_button[0], mouseData=release_button[2])))),
              ctypes.sizeof(Input))


def click_mouse(mouse_keycode: int, x: int = None, y: int = None) -> None:
    """
    :param mouse_keycode which mouse keycode we want to click
    :param x mouse x position
    :param y mouse y position
    """
    if x and y is not None:
        set_position(x, y)
    press_mouse(mouse_keycode)
    release_mouse(mouse_keycode)


def scroll(scroll_value: int, x: int = None, y: int = None) -> None:    
    """
    :param scroll_value scroll count
    :param x scroll x
    :param y scroll y
    """
    mouse_event(WIN32_WHEEL, x, y, dwData=scroll_value)


def send_mouse_event_to_window(window, mouse_keycode: int, x: int = None, y: int = None):
    lparam = (y << 16) | x
    user32.PostMessageW(window, mouse_keycode, 1, lparam)
    user32.PostMessageW(window, mouse_keycode, 0, lparam)
