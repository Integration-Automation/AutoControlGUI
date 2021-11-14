import sys

from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlException
from je_auto_control.utils.je_auto_control_exception.exception_tag import linux_import_error

if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error)

from je_auto_control.linux_with_x11.core.utils.x11_linux_display import display


def size():
    """
    get screen size
    """
    return display.screen().width_in_pixels, display.screen().height_in_pixels
