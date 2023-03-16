import sys
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import osx_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error)

import Quartz


def size() -> Tuple[int, int]:
    """
    get screen size
    """
    return Quartz.CGDisplayPixelsWide((Quartz.CGMainDisplayID())), Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
