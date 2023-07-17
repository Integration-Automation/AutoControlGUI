import sys

from je_auto_control import execute_action
from je_auto_control import test_record_instance

test_list = None
test_record_instance.init_record = True
if sys.platform in ["win32", "cygwin", "msys"]:
    test_list = [
        ["AC_set_record_enable", {"set_enable": True}],
        ["AC_type_keyboard", {"keycode": 65}],
        ["AC_mouse_left", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
        ["AC_get_mouse_position"],
        ["AC_press_mouse", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
        ["AC_release_mouse", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
        ["AC_type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
        ["AC_generate_xml_report"]
    ]

elif sys.platform in ["linux", "linux2"]:
    test_list = [
        ["AC_set_record_enable", {"set_enable": True}],
        ["AC_type_keyboard", {"keycode": 38}],
        ["AC_mouse_left", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
        ["AC_get_mouse_position"],
        ["AC_press_mouse", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
        ["AC_release_mouse", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
        ["AC_type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
        ["AC_generate_xml_report"]
    ]
elif sys.platform in ["darwin"]:
    test_list = [
        ["AC_set_record_enable", {"set_enable": True}],
        ["AC_type_keyboard", {"keycode": 0x00}],
        ["AC_mouse_left", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
        ["AC_get_mouse_position"],
        ["AC_press_mouse", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
        ["AC_release_mouse", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
        ["AC_type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
        ["AC_generate_xml_report"]
    ]
print("\n\n")
execute_action(test_list)
