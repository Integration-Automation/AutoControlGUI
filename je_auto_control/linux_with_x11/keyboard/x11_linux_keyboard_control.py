import sys
import time

from je_auto_control.utils.exception.exception_tags import linux_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error)

from je_auto_control.linux_with_x11.core.utils.x11_linux_display import display
from Xlib.ext.xtest import fake_input
from Xlib import X, protocol


def press_key(keycode: int) -> None:
    """
    :param keycode which keycode we want to press
    """
    time.sleep(0.01)
    fake_input(display, X.KeyPress, keycode)
    display.sync()


def release_key(keycode: int) -> None:
    """
    :param keycode which keycode we want to release
    """
    time.sleep(0.01)
    fake_input(display, X.KeyRelease, keycode)
    display.sync()

def send_key_event_to_window(window_id, keycode: int):
    window = display.create_resource_object('window', window_id)
    event = protocol.event.KeyPress(
        time=X.CurrentTime,
        root=display.screen().root,
        window=window,
        same_screen=1,
        child=X.NONE,
        root_x=0, root_y=0, event_x=0, event_y=0,
        state=0,
        detail=keycode
    )
    window.send_event(event, propagate=True)
    event.type = X.KeyRelease
    window.send_event(event, propagate=True)
    display.flush()