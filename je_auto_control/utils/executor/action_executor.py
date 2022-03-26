import sys
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
from je_auto_control.utils.exception.exception_tag import action_is_null_error
from je_auto_control.utils.exception.exception_tag import cant_execute_action_error
from je_auto_control.utils.exception.exceptions import AutoControlActionException

from je_auto_control.utils.test_record.record_test_class import test_record

event_dict = {
    # mouse
    "mouse_left": click_mouse,
    "mouse_right": click_mouse,
    "mouse_middle": click_mouse,
    "mouse_table": mouse_table,
    "position": position,
    "press_mouse": press_mouse,
    "release_mouse": release_mouse,
    "scroll": scroll,
    "set_position": set_position,
    "special_table": special_table,
    # keyboard
    "keys_table": keys_table,
    "type_key": type_key,
    "press_key": press_key,
    "release_key": release_key,
    "check_key_is_press": check_key_is_press,
    "write": write,
    "hotkey": hotkey,
    # image
    "locate_all_image": locate_all_image,
    "locate_image_center": locate_image_center,
    "locate_and_click": locate_and_click,
    # screen
    "size": size,
    "screenshot": screenshot
}


def execute_event(action: list):
    event = event_dict.get(action[0])
    if len(action) == 2:
        return event(**action[1])
    elif len(action) == 1:
        return event()
    else:
        raise AutoControlActionException(cant_execute_action_error)


def execute_action(action_list: list):
    """
    use to execute all action on action list(action file or program list)
    :param action_list the list include action
    for loop the list and execute action
    """
    flag = test_record.init_total_record
    """
    if init_total_record original is True
    make it False and then make it return
    """
    if flag:
        test_record.init_total_record = False
    execute_record_string = ""
    if action_list is None:
        raise AutoControlActionNullException(action_is_null_error)
    for action in action_list:
        try:
            execute_event(action)
            temp_string = "execute: " + str(action)
            print(temp_string)
            test_record.record_list.append(temp_string)
            execute_record_string = "".join([execute_record_string, temp_string + "\n"])
        except Exception as error:
            print(repr(error), file=sys.stderr)
            test_record.error_record_list.append([action, repr(error)])
    if flag:
        test_record.init_total_record = True
    return execute_record_string
