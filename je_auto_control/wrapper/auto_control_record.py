"""Start and stop input recording, and save what was recorded.

macOS used to be refused here outright: the recorder existed but wiring it up
would have put an ``NSApplication`` and a blocking run loop into the import of
the platform wrapper. It no longer does — capture runs on a Quartz event tap
on its own thread — so the refusal is gone and every platform with a recorder
goes down the same path. A macOS session without Accessibility permission now
fails where that is actually true, in the tap, naming the permission.
"""
import os
import threading
from typing import Optional

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


def stop_record_timeline() -> list:
    """
    停止錄製並回傳含放開、滾輪與間隔時間的完整事件
    Stop recording and return press *and* release, wheel, and ``delta_ms``

    :func:`stop_record` reports only what was pressed, which is not enough to
    reproduce a session: a drag looks like a click, scrolling is missing, and
    every step replays at once. These events feed
    :func:`je_auto_control.utils.input_macro.replay_timeline` directly.

    Returns an empty list on a platform whose recorder cannot supply it.
    """
    autocontrol_logger.info("stop_record_timeline")
    try:
        collect = getattr(recorder, "stop_record_timeline", None)
        if collect is None:
            autocontrol_logger.error(
                "stop_record_timeline: this recorder has no timeline support")
            return []
        events = collect()
        record_action_to_list("stop_record_timeline", None)
        return list(events)
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError,
            AutoControlException) as error:
        record_action_to_list("stop_record_timeline", None, repr(error))
        autocontrol_logger.error(f"stop_record_timeline, failed: {repr(error)}")
        return []


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
