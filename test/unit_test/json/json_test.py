import os

from je_auto_control import read_action_json
from je_auto_control import write_action_json

test_list = [
    ["AC_type_keyboard", {"keycode": 0x00}],
    ["AC_mouse_left", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
    ["AC_get_mouse_position"],
    ["AC_press_mouse", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
    ["AC_release_mouse", {"mouse_keycode": "AC_mouse_left", "x": 500, "y": 500}],
]

write_action_json(os.getcwd() + "/test1.json", test_list)
read_json = read_action_json(os.getcwd() + "/test1.json")
print(read_json)
