import sys

from je_auto_control.utils.je_auto_control_exception.exception_tag import osx_import_error
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlException

if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error)

import Quartz


def check_key_is_press(keycode: int):
    """
    :param keycode which keycode we want to check
    """
    return Quartz.CGEventSourceKeyState(0, keycode)

