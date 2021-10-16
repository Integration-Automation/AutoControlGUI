import sys

from je_auto_control.utils.action_executer.action_execute import execute_action
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlException
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlJsonActionException
from je_auto_control.wrapper.auto_control_keyboard import type_key
from je_auto_control.wrapper.auto_control_mouse import click_mouse
from je_auto_control.wrapper.platform_wrapper import recorder

event_dict = {"mouse_left": "click_mouse", "mouse_right": "click_mouse", "mouse_middle": "click_mouse",
              "keyboard": "type_key"}


def record_mouse():
    recorder.record_mouse()


def stop_record_mouse():
    action_queue = recorder.stop_record_mouse()
    if action_queue is None:
        raise AutoControlJsonActionException
    for mouse_action in action_queue.queue:
        click_mouse(mouse_action[0], mouse_action[1], mouse_action[2])


def record_keyboard():
    recorder.record_keyboard()


def stop_record_keyboard():
    action_queue = recorder.stop_record_keyboard()
    if action_queue is None:
        raise AutoControlJsonActionException
    for keyboard_action in action_queue.queue:
        type_key(keyboard_action[1])


def record():
    if sys.platform == "darwin":
        raise AutoControlException("macos can't use recorder")
    recorder.record()


def stop_record():
    if sys.platform == "darwin":
        raise AutoControlException("macos can't use recorder")
    action_queue = recorder.stop_record()
    if action_queue is None:
        raise AutoControlJsonActionException
    action_list = list(action_queue.queue)
    execute_action(action_list)


if __name__ == "__main__":
    record()
    from time import sleep
    sleep(5)
    stop_record()
    sleep(2)
