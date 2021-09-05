import sys

if sys.platform not in ["linux", "linux2"]:
    raise Exception("should be only loaded on linux")

import os
from Xlib.display import Display

display = Display(os.environ['DISPLAY'])