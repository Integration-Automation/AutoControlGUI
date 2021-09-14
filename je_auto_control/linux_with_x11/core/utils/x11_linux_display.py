import sys

if sys.platform not in ["linux", "linux2"]:
    raise Exception("should be only loaded on linux")

import os
from Xlib.display import Display
"""
get x system display
"""
display = Display(os.environ['DISPLAY'])
