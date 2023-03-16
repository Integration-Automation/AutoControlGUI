import sys

from je_auto_control.utils.exception.exception_tags import linux_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error)

import os
from Xlib.display import Display

# get x system display
display = Display(os.environ['DISPLAY'])
