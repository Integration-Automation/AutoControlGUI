import sys

if sys.platform not in ["linux", "linux2"]:
    raise Exception("should be only loaded on linux")

from Xlib import X
from Xlib.ext.xtest import fake_input

from je_auto_control.linux_with_x11.core.utils.x11_linux_display import display

x11_linux_mouse_left = 1
x11_linux_mouse_middle = 2
x11_linux_mouse_right = 3
x11_linux_scroll_direction_up = 4
x11_linux_scroll_direction_down = 5
x11_linux_scroll_direction_left = 6
x11_linux_scroll_direction_right = 7


def position():
    coord = display.screen().root.query_pointer()._data
    return coord["root_x"], coord["root_y"]


def set_position(x, y):
    fake_input(display, X.MotionNotify, x=x, y=y)
    display.sync()


def press_mouse(mouse_keycode):
    fake_input(display, X.ButtonPress, mouse_keycode)
    display.sync()


def release_mouse(mouse_keycode):
    fake_input(display, X.ButtonRelease, mouse_keycode)
    display.sync()


def click_mouse(mouse_keycode):
    press_mouse(mouse_keycode)
    release_mouse(mouse_keycode)


def scroll(scroll_value, scroll_direction):
    """"
    scroll_direction = 4 : direction up
    scroll_direction = 5 : direction down
    scroll_direction = 6 : direction left
    scroll_direction = 7 : direction right
    """
    for i in range(scroll_value):
        click_mouse(scroll_direction)

