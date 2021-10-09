import sys

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise Exception("should be only loaded on windows")

from je_auto_control.windows.listener import win32_keyboard_listener
from je_auto_control.windows.listener import win32_mouse_listener

from je_auto_control.windows.mouse.win32_ctype_mouse_control import click_mouse

from je_auto_control.windows.keyboard.win32_ctype_keyboard_control import press_key
from je_auto_control.windows.keyboard.win32_ctype_keyboard_control import release_key

