import os
import sys
import threading
from typing import Optional

from je_auto_control.utils.exception.exception_tags import macos_record_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.exception.exceptions import AutoControlJsonActionException
from je_auto_control.utils.json.json_file import write_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
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
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError, AutoControlException, AutoControlJsonActionException) as error:
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
        new_list = []
        for action in action_list:
            if action[0] == "AC_type_keyboard":
                new_list.append([action[0], {"keycode": action[1]}])
            else:
                new_list.append([action[0], {"x": action[1], "y": action[2]}])
        record_action_to_list("stop_record", None)
        return new_list
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError, AutoControlException, AutoControlJsonActionException) as error:
        record_action_to_list("stop_record", None, repr(error))
        autocontrol_logger.error(f"stop_record, failed: {repr(error)}")


def record_to_json(output_path: str, *, stop_event: threading.Event,
                   timeout: Optional[float] = None) -> list:
    """
    Record input until ``stop_event`` is set (or ``timeout``), saving to JSON.

    The caller owns ``stop_event`` and signals it (for example when the user
    presses Enter), keeping terminal I/O out of this headless helper.

    :param output_path: 錄製結果的儲存路徑
    :param stop_event: 設定後即停止錄製的事件旗標
    :param timeout: 最長錄製秒數，None 代表等到 stop_event 為止
    :return: 錄製到的動作列表
    """
    target = os.path.realpath(output_path)
    record()
    try:
        stop_event.wait(timeout)
    finally:
        actions = stop_record() or []
    write_action_json(target, actions)
    return actions
