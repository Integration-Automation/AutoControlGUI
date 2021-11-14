import sys

from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlException
from je_auto_control.utils.je_auto_control_exception.exception_tag import linux_import_error

if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error)

import os
from Xlib.display import Display
"""
get x system display
"""
display = Display(os.environ['DISPLAY'])
