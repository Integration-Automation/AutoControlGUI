"""Owned X11 recording subscription without replacing or stopping the global listener."""
from queue import Queue
from typing import Any, Optional

from je_auto_control.linux_with_x11.listener.x11_linux_listener import xwindows_listener
from je_auto_control.linux_with_x11.record.x11_linux_record import detail_dict, type_dict


class X11OwnedRecorder:
    """Own one bounded queue subscription; script/global recording remains independent."""

    def __init__(self) -> None:
        self._queue: Queue[Any] = Queue()
        self._identifier: Optional[str] = None

    def record(self) -> None:
        """Subscribe to the existing listener rather than changing its legacy record flag."""
        if self._identifier is None:
            # pylint: disable=protected-access  # reason: internal listener subscription ownership
            self._identifier = xwindows_listener.handler._subscribe_recording(self._queue)
            # pylint: enable=protected-access

    def stop_record(self) -> Queue[Any]:
        """Unsubscribe only this recorder and retain the historical action shape."""
        if self._identifier is not None:
            # pylint: disable=protected-access  # reason: internal listener subscription ownership
            xwindows_listener.handler._unsubscribe_recording(self._identifier)
            # pylint: enable=protected-access
            self._identifier = None
        result: Queue[Any] = Queue()
        for event in self._queue.queue:
            if event[0] == 3:
                result.put((type_dict[3], event[1]))
            elif event[0] == 5 and event[1] in detail_dict:
                result.put((detail_dict[event[1]], event[2], event[3]))
        return result
