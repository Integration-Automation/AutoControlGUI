import sys

if sys.platform not in ["darwin"]:
    raise Exception("should be only loaded on MacOS")

import Quartz


def check_key_is_press(keycode):
    return Quartz.CGEventSourceKeyState(0, keycode)

