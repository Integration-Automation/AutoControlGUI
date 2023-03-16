import sys

from je_auto_control.utils.exception.exception_tags import osx_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error)

import Quartz


def check_key_is_press(keycode: int) -> bool:
    """
    :param keycode which keycode we want to check
    """
    return Quartz.CGEventSourceKeyState(0, keycode)
