import sys

if sys.platform not in ["darwin"]:
    raise Exception("should be only loaded on MacOS")

import Quartz


def check_key_is_press(key_code):
    return Quartz.CGEventSourceKeyState(0, key_code)

