import sys
from typing import Any, Dict, List, Optional
from queue import Queue

from je_auto_control.utils.exception.exception_tags import windows_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

from je_auto_control.windows.record.win32_input_hook import (
    Win32InputHook, timeline,
)

# Legacy queue entries: the down-event half, shaped as executor commands.
_LEGACY_MOUSE_COMMAND = {"left": "AC_mouse_left", "right": "AC_mouse_right",
                         "middle": "AC_mouse_middle"}


class Win32Recorder:
    """
    Win32Recorder
    Windows 錄製器
    - 可同時錄製滑鼠與鍵盤事件
    - 可選擇只錄製滑鼠或鍵盤

    Capture runs through :class:`Win32InputHook`, which records releases, wheel
    movement and timing as well as presses. ``stop_record`` still returns the
    historical down-events-only queue so existing callers are unaffected; use
    ``stop_record_timeline`` for everything needed to reproduce the session.
    """

    def __init__(self):
        self.hook: Optional[Win32InputHook] = None
        self.record_queue: Optional[Queue] = None
        self.result_queue: Optional[Queue] = None
        self._kinds: tuple = ("keyboard", "mouse")

    def _start(self, kinds: tuple) -> None:
        self._kinds = kinds
        self.hook = Win32InputHook()
        self.record_queue = Queue()
        self.hook.start()

    def _stop(self) -> List[Dict[str, Any]]:
        if self.hook is None:
            return []
        events = [event for event in self.hook.stop()
                  if self._wanted(event)]
        self.hook = None
        return events

    def _wanted(self, event: Dict[str, Any]) -> bool:
        keyboard = event.get("op", "").startswith("key_")
        return ("keyboard" if keyboard else "mouse") in self._kinds

    def _as_queue(self, events: List[Dict[str, Any]]) -> Queue:
        """The historical shape: one executor command per press, no releases."""
        queue: Queue = Queue()
        for event in events:
            operation = event.get("op")
            if operation == "key_down":
                queue.put(("AC_type_keyboard", int(event.get("vk", 0))))
            elif operation == "mouse_down":
                command = _LEGACY_MOUSE_COMMAND.get(event.get("button", ""))
                if command:
                    queue.put((command, int(event.get("x", 0)),
                               int(event.get("y", 0))))
        self.record_queue = None
        self.result_queue = queue
        return queue

    def record(self) -> None:
        """
        開始錄製滑鼠與鍵盤事件
        Start recording both mouse and keyboard events
        """
        self._start(("keyboard", "mouse"))

    def stop_record(self) -> Queue:
        """
        停止錄製並回傳事件
        Stop recording and return recorded events
        """
        return self._as_queue(self._stop())

    def stop_record_timeline(self) -> List[Dict[str, Any]]:
        """
        停止錄製並回傳含放開、滾輪與間隔時間的完整事件
        Stop recording and return press *and* release, wheel and ``delta_ms``

        Ready for :func:`je_auto_control.utils.input_macro.replay_timeline`.
        """
        return timeline(self._stop())

    def record_mouse(self) -> None:
        """
        開始錄製滑鼠事件
        Start recording mouse events
        """
        self._start(("mouse",))

    def stop_record_mouse(self) -> Queue:
        """
        停止錄製滑鼠事件並回傳結果
        Stop recording mouse events and return results
        """
        return self._as_queue(self._stop())

    def record_keyboard(self) -> None:
        """
        開始錄製鍵盤事件
        Start recording keyboard events
        """
        self._start(("keyboard",))

    def stop_record_keyboard(self) -> Queue:
        """
        停止錄製鍵盤事件並回傳結果
        Stop recording keyboard events and return results
        """
        return self._as_queue(self._stop())


# 全域錄製器實例 Global recorder instance
win32_recorder = Win32Recorder()