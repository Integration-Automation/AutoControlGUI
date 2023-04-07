import sys

from je_auto_control import execute_action
from je_auto_control import test_record_instance

test_list = None
test_record_instance.init_record = True
if sys.platform in ["win32", "cygwin", "msys"]:
    test_list = [
        ["set_record_enable", {"set_enable": True}],
        ["type_keyboard", {"keycode": 65}],
        ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["get_mouse_position"],
        ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
        ["generate_json_report"],
    ]

elif sys.platform in ["linux", "linux2"]:
    test_list = [
        ["set_record_enable", {"set_enable": True}],
        ["type_keyboard", {"keycode": 38}],
        ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["get_mouse_position"],
        ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
        ["generate_json_report"],
    ]
elif sys.platform in ["darwin"]:
    test_list = [
        ["set_record_enable", {"set_enable": True}],
        ["type_keyboard", {"keycode": 0x00}],
        ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["get_mouse_position"],
        ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
        ["generate_json_report"],
    ]
print("\n\n")
execute_action(test_list)
