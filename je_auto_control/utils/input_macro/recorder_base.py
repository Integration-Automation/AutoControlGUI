"""Platform-neutral shaping of recorded input, and the recorder base class.

Windows and macOS capture input through entirely different OS machinery — a
low-level ``WH_KEYBOARD_LL`` hook driven by a message pump, and a Quartz
``CGEventTap`` driven by a run loop — but everything *after* the capture is
identical: the same event dictionaries, the same three ways of asking for
them, and the same two output shapes. That part belongs here rather than
being copied into the second backend.

* :func:`timeline` turns raw timestamped events into the ``delta_ms`` form
  :func:`je_auto_control.utils.input_macro.replay_timeline` plays back.
* :func:`legacy_action_queue` produces the historical down-events-only queue
  that :func:`je_auto_control.wrapper.auto_control_record.stop_record` and the
  executor have always been handed.
* :class:`InputRecorder` is the ``record`` / ``record_mouse`` /
  ``record_keyboard`` surface every platform recorder exposes. A backend
  supplies only :meth:`InputRecorder.new_hook`.

The divergence this prevents is not hypothetical and would be silent: a
recording made on one OS has to replay on the other, and two hand-written
copies of the queue shaping drift without anything going red.

**Everything typed while recording is captured, passwords included.** Callers
must treat the result as sensitive.
"""
from queue import Queue
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: A hook left installed grows its event list forever. Recording is bounded so
#: a forgotten session cannot consume the process.
MAX_EVENTS = 20000

#: Legacy queue entries: the down-event half, shaped as executor commands.
LEGACY_MOUSE_COMMAND = {"left": "AC_mouse_left", "right": "AC_mouse_right",
                        "middle": "AC_mouse_middle"}

#: Both capture kinds, which is what a plain ``record()`` asks for.
ALL_KINDS: Tuple[str, ...] = ("keyboard", "mouse")


def event_kind(event: Dict[str, Any]) -> str:
    """Return ``"keyboard"`` or ``"mouse"`` for one raw event."""
    return "keyboard" if str(event.get("op", "")).startswith("key_") else "mouse"


def timeline(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw events to ``delta_ms`` form for ``replay_timeline``.

    The first event has no gap before it; every later one carries the real
    pause that preceded it, which is what makes a replay track the original
    pace.
    """
    out: List[Dict[str, Any]] = []
    previous: Optional[float] = None
    for event in events:
        moment = float(event.get("time", 0.0))
        item = {key: value for key, value in event.items() if key != "time"}
        item["delta_ms"] = 0 if previous is None else max(
            0, int((moment - previous) * 1000))
        out.append(item)
        previous = moment
    return out


def legacy_action_queue(events: List[Dict[str, Any]]) -> Queue:
    """The historical shape: one executor command per press, no releases."""
    queue: Queue = Queue()
    for event in events:
        operation = event.get("op")
        if operation == "key_down":
            queue.put(("AC_type_keyboard", int(event.get("vk", 0))))
        elif operation == "mouse_down":
            command = LEGACY_MOUSE_COMMAND.get(event.get("button", ""))
            if command:
                queue.put((command, int(event.get("x", 0)),
                           int(event.get("y", 0))))
    return queue


class InputRecorder:
    """``record`` / ``stop_record`` over a platform hook, with timeline output.

    ``stop_record`` keeps returning the down-events-only queue so existing
    callers are unaffected; ``stop_record_timeline`` returns everything a
    replay needs — releases, wheel movement and per-event gaps.
    """

    def __init__(self) -> None:
        self.hook: Any = None
        self.record_queue: Optional[Queue] = None
        self.result_queue: Optional[Queue] = None
        self._kinds: Tuple[str, ...] = ALL_KINDS

    def new_hook(self) -> Any:
        """Return a fresh, unstarted platform hook. Backends override this."""
        raise NotImplementedError

    # -- capture -----------------------------------------------------------
    def _start(self, kinds: Sequence[str]) -> None:
        self._kinds = tuple(kinds)
        self.hook = self.new_hook()
        self.record_queue = Queue()
        self.hook.start()

    def _stop(self) -> List[Dict[str, Any]]:
        if self.hook is None:
            return []
        events = [event for event in self.hook.stop()
                  if event_kind(event) in self._kinds]
        self.hook = None
        return events

    def _as_queue(self, events: List[Dict[str, Any]]) -> Queue:
        queue = legacy_action_queue(events)
        self.record_queue = None
        self.result_queue = queue
        return queue

    # -- public ------------------------------------------------------------
    def record(self) -> None:
        """
        開始錄製滑鼠與鍵盤事件
        Start recording both mouse and keyboard events
        """
        self._start(ALL_KINDS)

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
