import sys

from je_auto_control.utils.exception.exception_tags import macos_record_error
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.exception.exceptions import AutoControlJsonActionException
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.platform_wrapper import recorder


def record() -> None:
    """
    start record keyboard and mouse event until stop_record
    """
    try:
        if sys.platform == "darwin":
            raise AutoControlException(macos_record_error)
        record_action_to_list("record", None)
        return recorder.record()
    except Exception as error:
        record_action_to_list("record", None, repr(error))
        print(repr(error), file=sys.stderr)


def stop_record() -> list:
    """
    stop current record
    """
    try:
        if sys.platform == "darwin":
            raise AutoControlException(macos_record_error)
        action_queue = recorder.stop_record()
        if action_queue is None:
            raise AutoControlJsonActionException
        action_list = list(action_queue.queue)
        new_list = list()
        for action in action_list:
            if action[0] == "type_key":
                new_list.append([action[0], dict([["keycode", action[1]]])])
            else:
                new_list.append([action[0], dict(zip(["mouse_keycode", "x", "y"], [action[0], action[1], action[2]]))])
        record_action_to_list("stop_record", None)
        return new_list
    except Exception as error:
        record_action_to_list("stop_record", None, repr(error))
        print(repr(error), file=sys.stderr)
