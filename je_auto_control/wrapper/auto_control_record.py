from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlRecordQueueException
from je_auto_control.wrapper.auto_control_mouse import click_mouse
from je_auto_control.wrapper.auto_control_keyboard import type_key
from je_auto_control.wrapper.platform_wrapper import recorder

event_dict = {"mouse_left": click_mouse, "mouse_right": click_mouse, "mouse_middle": click_mouse, "keyboard": type_key}


def record_mouse():
    recorder.record_mouse()


def stop_record_mouse():
    action_queue = recorder.stop_record_mouse()
    if action_queue is None:
        raise AutoControlRecordQueueException
    for mouse_action in action_queue.queue:
        print(mouse_action)
        click_mouse(mouse_action[0], mouse_action[1], mouse_action[2])


def record_keyboard():
    recorder.record_keyboard()


def stop_record_keyboard():
    action_queue = recorder.stop_record_keyboard()
    if action_queue is None:
        raise AutoControlRecordQueueException
    for keyboard_action in action_queue.queue:
        print(keyboard_action)
        type_key(keyboard_action[1])


def record():
    recorder.record()


def stop_record():
    action_queue = recorder.stop_record()
    if action_queue is None:
        raise AutoControlRecordQueueException
    for action in action_queue.queue:
        print(action)
        if event_dict.get(action[0]) is type(click_mouse):
            click_mouse(action[0], action[1], action[2])
        else:
            type_key(action[1])


if __name__ == "__main__":
    record_mouse()
    from time import sleep
    sleep(10)
    stop_record_mouse()
