from je_auto_control import AutoControlActionException
from je_auto_control import AutoControlActionNullException
from je_auto_control import check_key_is_press
from je_auto_control import click_mouse
from je_auto_control import hotkey
from je_auto_control import keys_table
from je_auto_control import locate_all_image
from je_auto_control import locate_and_click
from je_auto_control import locate_image_center
from je_auto_control import mouse_table
from je_auto_control import position
from je_auto_control import press_key
from je_auto_control import press_mouse
from je_auto_control import release_key
from je_auto_control import release_mouse
from je_auto_control import screenshot
from je_auto_control import scroll
from je_auto_control import set_position
from je_auto_control import size
from je_auto_control import special_table
from je_auto_control import type_key
from je_auto_control import write
from je_auto_control.utils.je_auto_control_exception.exception_tag import action_is_null_error
from je_auto_control.utils.je_auto_control_exception.exception_tag import cant_execute_action_error

event_dict = {
    # mouse
    "mouse_left": ("click_mouse", click_mouse),
    "mouse_right": ("click_mouse", click_mouse),
    "mouse_middle": ("click_mouse", click_mouse),
    "mouse_table": ("mouse_table", mouse_table),
    "position": ("position", position),
    "press_mouse": ("press_mouse", press_mouse),
    "release_mouse": ("release_mouse", release_mouse),
    "scroll": ("scroll", scroll),
    "set_position": ("set_position", set_position),
    "special_table": ("special_table", special_table),
    # keyboard
    "keys_table": ("keys_table", keys_table),
    "type_key": ("type_key", type_key),
    "press_key": ("press_key", press_key),
    "release_key": ("release_key", release_key),
    "check_key_is_press": ("check_key_is_press", check_key_is_press),
    "write": ("write", write),
    "hotkey": ("hotkey", hotkey),
    # image
    "locate_all_image": ("locate_all_image", locate_all_image),
    "locate_image_center": ("locate_image_center", locate_image_center),
    "locate_and_click": ("locate_and_click", locate_and_click),
    # screen
    "size": ("size", size),
    "screenshot": ("screenshot", screenshot)
}


def execute_event(action):
    event = event_dict.get(action[0])
    if event[0] in ["click_mouse"]:
        event[1](action[0], action[1], action[2])
    elif event[0] in ["type_key", "press_key", "release_key", "check_key_is_press", "write"]:
        event[1](action[1])
    elif event[0] in ["position", "record", "stop_record", "size"]:
        event[1]()
    elif event[0] in ["set_position", "screenshot"]:
        event[1](action[1], action[2])
    elif event[0] in ["locate_all_image", "locate_image_center", "press_mouse", "release_mouse"]:
        event[1](action[1], action[2], action[3])
    elif event[0] in ["scroll", "locate_and_click"]:
        event[1](action[1], action[2], action[3], action[4])


def execute_action(action_list: list):
    """
    :param action_list the list include action
    for loop the list and execute action
    """
    execute_record_string = ""
    if action_list is None:
        raise AutoControlActionNullException(action_is_null_error)
    for action in action_list:
        try:
            execute_event(action)
        except AutoControlActionException:
            raise AutoControlActionException(cant_execute_action_error)
        temp_string = "execute: " + str(action)
        print(temp_string)
        execute_record_string = "".join([execute_record_string, temp_string + "\n"])
    return execute_record_string


if __name__ == "__main__":
    import sys

    test_list = None
    if sys.platform in ["win32", "cygwin", "msys"]:
        test_list = [
            ("type_key", 65),
            ("mouse_left", 500, 500),
            ("position", "position"),
            ("press_mouse", "mouse_left", 500, 500),
            ("release_mouse", "mouse_left", 500, 500),
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
    print("\n\n")
    print(execute_action(test_list))
