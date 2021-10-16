from je_auto_control import type_key
from je_auto_control import click_mouse
from je_auto_control import write

from je_auto_control import AutoControlActionNullException

event_dict = {"mouse_left": "click_mouse", "mouse_right": "click_mouse", "mouse_middle": "click_mouse", "keyboard": "type_key"}


def execute_action(action_list):
    if action_list is None:
        raise AutoControlActionNullException
    for action in action_list:
        if event_dict.get(action[0]) == "click_mouse":
            click_mouse(action[0], action[1], action[2])
        elif event_dict.get(action[0]) == "type_key":
            type_key(action[1])


if __name__ == "__main__":
    import sys
    test_list = None
    if sys.platform in ["win32", "cygwin", "msys"]:
        test_list = [("keyboard", 65), ("keyboard", 0x41), ("keyboard", 0x41), ("keyboard", 0x41)]
    elif sys.platform in ["linux", "linux2"]:
        test_list = [("keyboard", 0x00), ("keyboard", 0x00), ("keyboard", 0x00), ("keyboard", 0x00)]
    elif sys.platform in ["darwin"]:
        test_list = [("keyboard", 38), ("keyboard", 38), ("keyboard", 38), ("keyboard", 38)]
    execute_action(test_list)

