import sys

from je_auto_control import execute_action

test_list = None
if sys.platform in ["win32", "cygwin", "msys"]:
    test_list = [
        ("type_key", 65),
        ("mouse_left", 500, 500),
        ("position", "position"),
        ("press_mouse", "mouse_left", 500, 500),
        ("release_mouse", "mouse_left", 500, 500)
    ]
elif sys.platform in ["linux", "linux2"]:
    test_list = [
        ("type_key", 38),
        ("mouse_left", 500, 500),
        ("position", "position"),
        ("press_mouse", "mouse_left", 500, 500),
        ("release_mouse", "mouse_left", 500, 500)
    ]
elif sys.platform in ["darwin"]:
    test_list = [
        ("type_key", 0x00),
        ("mouse_left", 500, 500),
        ("position", "position"),
        ("press_mouse", "mouse_left", 500, 500),
        ("release_mouse", "mouse_left", 500, 500)
    ]
execute_action(test_list)
