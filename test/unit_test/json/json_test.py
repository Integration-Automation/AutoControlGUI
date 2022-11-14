import os

from je_auto_control import read_action_json
from je_auto_control import write_action_json

test_list = [
    ["type_key", {"keycode": 0x00}],
    ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
    ["position"],
    ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
    ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
]

write_action_json(os.getcwd() + "/test1.json", test_list)
read_json = read_action_json(os.getcwd() + "/test1.json")
print(read_json)
