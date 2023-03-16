import sys
import time

from je_auto_control.utils.exception.exception_tags import linux_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error)

from je_auto_control.linux_with_x11.core.utils.x11_linux_display import display
from Xlib.ext.xtest import fake_input
from Xlib import X


def press_key(keycode: int) -> None:
    """
    :param keycode which keycode we want to press
    """
    try:
        time.sleep(0.01)
        fake_input(display, X.KeyPress, keycode)
        display.sync()
    except Exception as error:
        print(repr(error), file=sys.stderr)


def release_key(keycode: int) -> None:
    """
    :param keycode which keycode we want to release
    """
    try:
        time.sleep(0.01)
        fake_input(display, X.KeyRelease, keycode)
        display.sync()
    except Exception as error:
        print(repr(error), file=sys.stderr)
