"""macOS physical presence: a listen-only session event tap that counts hardware events, plus console lock state.

An event posted by a process carries that process's id in
``kCGEventSourceUnixProcessID``; a hardware event comes from the HID system
state. Mistaking a person for an injection would let a task take over while
someone is at the keyboard, so the rule only ever errs the other way: an event
counts as injected only when it names a positive process id *and* its source
state is not the HID system state. Everything else counts as physical.

The tap needs the Accessibility (or Input Monitoring) permission; without it
``CGEventTapCreate`` returns nothing and the source refuses to start. Whether
the console is usable comes from ``CGSessionCopyCurrentDictionary``: on the
console and with the screen not locked.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_platform import require_poll_timeout

_KEY_DOWN, _KEY_UP = 10, 11
_DOWN = {1: 'left', 3: 'right', 25: 'other'}
_UP = {2: 'left', 4: 'right', 26: 'other'}
_OBSERVED = (1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 22, 25, 26, 27)
_TAP_DISABLED = frozenset((0xFFFFFFFE, 0xFFFFFFFF))
_SOURCE_PID_FIELD = 41
_SOURCE_STATE_FIELD = 45
_KEYCODE_FIELD = 9
_BUTTON_FIELD = 3
_HID_SYSTEM_STATE = 1
_RUN_TIMED_OUT = 3
_DRAIN_LIMIT = 1024


def _quartz() -> Any:
    # pylint: disable-next=import-outside-toplevel  # reason: pyobjc exists only on macOS hosts
    import Quartz
    return Quartz


def is_injected(source_pid: int, source_state: int) -> bool:
    """Count an event as injected only when a process posted it from a non-HID source state."""
    return source_pid > 0 and source_state != _HID_SYSTEM_STATE


class QuartzPresenceAPI:
    """Own one listen-only event tap and its run loop source on one helper thread."""

    def __init__(self, quartz: Callable[[], Any] = _quartz,
                 interactive: Callable[[Any], bool] | None = None) -> None:
        self._load = quartz
        self._interactive = interactive
        self._q: Any = None
        self._tap: Any = None
        self._source: Any = None
        self._loop: Any = None
        self._physical: Callable[[], None] | None = None
        self._thread: int | None = None
        self._held: set[tuple[str, int]] = set()
        self._failed = self._closed = False

    def _owner(self) -> None:
        if self._thread is not None and self._thread != threading.get_ident():
            raise AgentTaskError('physical presence tap belongs to a different thread')

    def open(self, physical: Callable[[], None]) -> None:
        """Create a listen-only session tap for key and pointer events on this thread's run loop."""
        if self._thread is not None or self._closed:
            raise AgentTaskError('physical presence observer cannot restart')
        self._thread, self._physical = threading.get_ident(), physical
        try:
            q = self._q = self._load()
            mask = sum(1 << kind for kind in _OBSERVED)
            self._tap = q.CGEventTapCreate(q.kCGSessionEventTap, q.kCGHeadInsertEventTap,
                                           q.kCGEventTapOptionListenOnly, mask, self._callback, None)
            if not self._tap:
                raise AgentTaskError('macOS physical presence needs the Accessibility permission')
            self._source = q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
            self._loop = q.CFRunLoopGetCurrent()
            q.CFRunLoopAddSource(self._loop, self._source, q.kCFRunLoopDefaultMode)
            q.CGEventTapEnable(self._tap, True)
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError, ImportError) as error:
            self.close()
            if isinstance(error, AgentTaskError):
                raise
            raise AgentTaskError('macOS physical presence observer could not start') from error

    def _track(self, kind: int, event: Any) -> None:
        q = self._q
        if kind in (_KEY_DOWN, _KEY_UP):
            key = ('key', int(q.CGEventGetIntegerValueField(event, _KEYCODE_FIELD)))
            (self._held.add if kind == _KEY_DOWN else self._held.discard)(key)
        elif kind in _DOWN or kind in _UP:
            button = int(q.CGEventGetIntegerValueField(event, _BUTTON_FIELD))
            key = ('button', button)
            (self._held.add if kind in _DOWN else self._held.discard)(key)

    def _callback(self, _proxy: Any, kind: int, event: Any, _refcon: Any) -> Any:
        try:
            if kind in _TAP_DISABLED:
                self._failed = True
                return event
            q = self._q
            pid = int(q.CGEventGetIntegerValueField(event, _SOURCE_PID_FIELD))
            state = int(q.CGEventGetIntegerValueField(event, _SOURCE_STATE_FIELD))
            if not is_injected(pid, state):
                self._track(kind, event)
                if self._physical is None:
                    raise AgentTaskError('physical presence callback is unavailable')
                self._physical()
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError, OverflowError):
            self._failed = True
        return event

    def _drain(self, timeout: float) -> None:
        q = self._q
        wait = timeout
        for _index in range(_DRAIN_LIMIT):
            if q.CFRunLoopRunInMode(q.kCFRunLoopDefaultMode, wait, True) == _RUN_TIMED_OUT:
                return
            wait = 0
            if self._failed:
                raise AgentTaskError('physical presence event tap failed or was disabled')
        raise AgentControlBusy('physical presence input queue is still active')

    def _console(self) -> bool:
        if self._interactive is not None:
            return self._interactive(self._q)
        session = self._q.CGSessionCopyCurrentDictionary()
        if not session:
            return False
        return bool(session.get('kCGSSessionOnConsoleKey')) and not session.get('CGSSessionScreenIsLocked')

    def poll(self, timeout: float) -> tuple[bool, bool]:
        """Run the tap for a bounded time, then report console usability and anything held."""
        self._owner()
        require_poll_timeout(timeout)
        if self._tap is None or self._closed or self._failed:
            raise AgentTaskError('physical presence observer is unavailable')
        self._drain(timeout)
        if self._failed or not self._q.CGEventTapIsEnabled(self._tap):
            raise AgentTaskError('physical presence event tap was disabled')
        return self._console(), bool(self._held) or self._hid_held()

    def _hid_held(self) -> bool:
        # A key or button already down before the tap started has no down event to track.
        q = self._q
        state = q.kCGEventSourceStateHIDSystemState
        return (any(q.CGEventSourceButtonState(state, button) for button in range(3))
                or any(q.CGEventSourceKeyState(state, key) for key in range(128)))

    def close(self) -> None:
        """Disable and invalidate the owned tap and remove its run loop source."""
        self._owner()
        self._closed = True
        q, tap, source, loop = self._q, self._tap, self._source, self._loop
        self._tap = self._source = self._loop = None
        if q is None or tap is None:
            return
        q.CGEventTapEnable(tap, False)
        if source is not None and loop is not None:
            q.CFRunLoopRemoveSource(loop, source, q.kCFRunLoopDefaultMode)
        q.CFMachPortInvalidate(tap)
