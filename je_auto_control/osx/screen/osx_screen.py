import sys

from je_auto_control.utils.je_auto_control_exception.exception_tag import osx_import_error
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlException

if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error)

import Quartz


def size():
    """
    get screen size
    """
    return Quartz.CGDisplayPixelsWide((Quartz.CGMainDisplayID())), Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
