import sys

from je_auto_control import AutoControlException
from je_auto_control import check_key_is_press
from je_auto_control import press_keyboard_key
from je_auto_control import release_keyboard_key

try:
    # because os key_code not equal
    while True:
        if sys.platform in ["win32", "cygwin", "msys"]:
            press_keyboard_key("A")
            # Windows key a or you can use check_key_is_press(ord("A"))
            if check_key_is_press("A"):
                sys.exit(0)
        elif sys.platform in ["darwin"]:
            press_keyboard_key("f5")
            # osx key F5
            if check_key_is_press(0x60):
                sys.exit(0)
        elif sys.platform in ["linux", "linux2"]:
            press_keyboard_key("a")
            # linux key a
            if check_key_is_press(0):
                sys.exit(0)
except AutoControlException:
    raise AutoControlException
finally:
    if sys.platform in ["win32", "cygwin", "msys"]:
        release_keyboard_key("A")
    elif sys.platform in ["darwin"]:
        release_keyboard_key("f5")
    elif sys.platform in ["linux", "linux2"]:
        release_keyboard_key("a")
