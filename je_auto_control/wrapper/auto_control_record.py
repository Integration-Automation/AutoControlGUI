import sys

from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlRecordException
from je_auto_control.utils.je_auto_control_exception.exception_tag import record_not_found_action_error
from je_auto_control.wrapper.auto_control_mouse import click_mouse
from je_auto_control.wrapper.auto_control_keyboard import type_key
from je_auto_control.wrapper.platform_wrapper import recorder

event_dict = {"mouse_left": "click_mouse", "mouse_right": "click_mouse", "mouse_middle": "click_mouse", "keyboard": "type_key"}


def record_mouse():
    recorder.record_mouse()


def stop_record_mouse():
    action_queue = recorder.stop_record_mouse()
    if action_queue is None:
        raise AutoControlRecordException
    for mouse_action in action_queue.queue:
        print(mouse_action)
        click_mouse(mouse_action[0], mouse_action[1], mouse_action[2])


def record_keyboard():
    recorder.record_keyboard()


def stop_record_keyboard():
    action_queue = recorder.stop_record_keyboard()
    if action_queue is None:
        raise AutoControlRecordException
    for keyboard_action in action_queue.queue:
        print(keyboard_action)
        type_key(keyboard_action[1])


def record():
    if sys.platform == "darwin":
        raise Exception("macos can't use recorder")
    recorder.record()


def stop_record():
    if sys.platform == "darwin":
        raise Exception("macos can't use recorder")
    action_queue = recorder.stop_record()
    if action_queue is None:
        raise AutoControlRecordException
    for action in action_queue.queue:
        if event_dict.get(action[0]) == "click_mouse":
            click_mouse(action[0], action[1], action[2])
        elif event_dict.get(action[0]) == "type_key":
            type_key(action[1])
        else:
            raise AutoControlRecordException(record_not_found_action_error)


if __name__ == "__main__":
    record()
    from time import sleep
    sleep(5)
    stop_record()
    sleep(2)


