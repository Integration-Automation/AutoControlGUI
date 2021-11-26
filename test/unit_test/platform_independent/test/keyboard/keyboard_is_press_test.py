import sys

from je_auto_control import check_key_is_press
from je_auto_control import press_key
from je_auto_control import release_key
from je_auto_control import AutoControlException

try:
    """
    because os key_code not equal
    """
    while True:
        if sys.platform in ["win32", "cygwin", "msys"]:
            press_key("A")
            """  
            windows key a or you can use check_key_is_press(ord("A"))
            """
            if check_key_is_press("A"):
                sys.exit(0)
        elif sys.platform in ["darwin"]:
            press_key("f5")
            """  
            osx key F5
            """
            if check_key_is_press(0x60):
                sys.exit(0)
        elif sys.platform in ["linux", "linux2"]:
            press_key("backspace")
            """  
            linux key backspace
            """
            if check_key_is_press(22):
                sys.exit(0)
except AutoControlException:
    raise AutoControlException
finally:
    if sys.platform in ["win32", "cygwin", "msys"]:
        release_key("A")
    elif sys.platform in ["darwin"]:
        release_key("f5")
    elif sys.platform in ["linux", "linux2"]:
        release_key("backspace")
