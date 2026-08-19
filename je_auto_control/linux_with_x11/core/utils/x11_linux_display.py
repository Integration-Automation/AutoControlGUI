
from je_auto_control.utils.exception.exception_tags import linux_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.platform_id import is_x11_unix

# Not "is this Linux" but "is this an X11 unix": a FreeBSD, OpenBSD or
# NetBSD desktop runs the same X server and the same python-Xlib, and
# nothing below is Linux-specific.
if not is_x11_unix():
    raise AutoControlException(linux_import_error_message)

import os
from Xlib.display import Display

# get x system display
display = Display(os.environ.get('DISPLAY', ':0'))
