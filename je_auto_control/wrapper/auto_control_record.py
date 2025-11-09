import sys

from je_auto_control.utils.exception.exception_tags import macos_record_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.exception.exceptions import AutoControlJsonActionException
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.platform_wrapper import recorder


def record() -> None:
    """
    start record keyboard and mouse event until stop_record
    """
    autocontrol_logger.info("record")
    try:
        if sys.platform == "darwin":
            raise AutoControlException(macos_record_error_message)
        record_action_to_list("record", None)
        recorder.record()
    except Exception as error:
        record_action_to_list("record", None, repr(error))
        autocontrol_logger.error(f"record, failed: {repr(error)}")


def stop_record() -> list:
    """
    stop current record
    """
    autocontrol_logger.info("stop_record")
    try:
        if sys.platform == "darwin":
            raise AutoControlException(macos_record_error_message)
        action_queue = recorder.stop_record()
        if action_queue is None:
            raise AutoControlJsonActionException
        action_list = list(action_queue.queue)
        new_list = list()
        for action in action_list:
            if action[0] == "AC_type_keyboard":
                new_list.append([action[0], dict([["keycode", action[1]]])])
            else:
                new_list.append([action[0], dict(zip(["mouse_keycode", "x", "y"], [action[0], action[1], action[2]]))])
        record_action_to_list("stop_record", None)
        return new_list
    except Exception as error:
        record_action_to_list("stop_record", None, repr(error))
        autocontrol_logger.error(f"stop_record, failed: {repr(error)}")
