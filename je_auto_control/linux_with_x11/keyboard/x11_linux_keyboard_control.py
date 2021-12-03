import sys
import time

from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlException
from je_auto_control.utils.je_auto_control_exception.exception_tag import linux_import_error

if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error)

from je_auto_control.linux_with_x11.core.utils.x11_linux_display import display
from Xlib.ext.xtest import fake_input
from Xlib import X


def press_key(keycode: int):
    """
    :param keycode which keycode we want to press
    """
    time.sleep(0.01)
    fake_input(display, X.KeyPress, keycode)
    display.sync()


def release_key(keycode: int):
    """
    :param keycode which keycode we want to release
    """
    time.sleep(0.01)
    fake_input(display, X.KeyRelease, keycode)
    display.sync()
