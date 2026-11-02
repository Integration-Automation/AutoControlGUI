"""X11 physical presence: XInput2 raw events from real devices, never from XTEST, plus logind lock state.

The source selects raw key, button and motion events for every device on the
root window, which is the only global XInput2 view. Events whose source device
is an XTEST slave (what ``xdotool`` and this package's own X11 backend inject
through) never count as physical. A device that ``uinput`` creates is not told
apart here: making one needs root or the ``uinput`` group.

Whether the seat is usable comes from logind (``Active`` and ``LockedHint`` of
``XDG_SESSION_ID``). Without logind or a session id the desktop counts as
locked, so the presence state never grants a lease on a guess.
"""
from __future__ import annotations

import os
import select
import shutil
import struct
import subprocess  # nosec B404  # reason: bounded read-only loginctl query with a fixed argv
import threading
import time
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_platform import require_poll_timeout

_GENERIC_EVENT = 35
_HIERARCHY_CHANGED = 11
_RAW_PRESS = {13: 'key', 15: 'button'}
_RAW_RELEASE = {14: 'key', 16: 'button'}
_RAW_EVENTS = frozenset((13, 14, 15, 16, 17))
_MASK = (1 << _HIERARCHY_CHANGED) | sum(1 << code for code in _RAW_EVENTS)
_SLAVES = frozenset((3, 4, 5))
_BUTTON_MASKS = 0x1F00
_RAW_HEADER = struct.Struct('=HIIHH')
_DRAIN_LIMIT = 1024


class LogindSession:
    """Read one session's ``Active``/``LockedHint`` through loginctl, at most once a second."""

    def __init__(self, session_id: str | None = None, *, runner: Callable[..., Any] = subprocess.run,
                 clock: Callable[[], float] = time.monotonic, interval: float = 1.0) -> None:
        self._session = session_id if session_id is not None else os.environ.get('XDG_SESSION_ID', '')
        self._runner, self._clock, self._interval = runner, clock, interval
        self._loginctl = shutil.which('loginctl')
        self._cached: tuple[float, bool] | None = None

    def _query(self) -> bool:
        if not self._loginctl or not self._session.isalnum():
            return False
        result = self._runner([self._loginctl, 'show-session', self._session, '-p', 'Active', '-p', 'LockedHint'],
                              capture_output=True, text=True, timeout=1, check=False, shell=False)
        if result.returncode != 0:
            return False
        values = {key: value for key, value in (line.split('=', 1) for line in result.stdout.splitlines()
                                                if '=' in line)}
        return values.get('Active') == 'yes' and values.get('LockedHint') == 'no'

    def interactive(self) -> bool:
        """Return whether the session is active and unlocked; any doubt reads as locked."""
        now = self._clock()
        if self._cached is not None and now - self._cached[0] < self._interval:
            return self._cached[1]
        try:
            value = self._query()
        except (OSError, ValueError, subprocess.SubprocessError):
            value = False
        self._cached = (now, value)
        return value


def _default_display() -> Any:
    # pylint: disable-next=import-outside-toplevel  # reason: python-Xlib exists only on X11 hosts
    from Xlib import display
    return display.Display()


class X11PresenceAPI:
    """Own one display connection and its root raw-event selection on one helper thread."""

    def __init__(self, display_factory: Callable[[], Any] = _default_display,
                 interactive: Callable[[], bool] | None = None) -> None:
        self._factory = display_factory
        self._interactive = interactive if interactive is not None else LogindSession().interactive
        self._display: Any = None
        self._opcode: int | None = None
        self._physical: Callable[[], None] | None = None
        self._thread: int | None = None
        self._injected: frozenset[int] = frozenset()
        self._devices: frozenset[int] = frozenset()
        self._held: set[tuple[str, int, int]] = set()
        self._closed = False

    def _owner(self) -> None:
        if self._thread is not None and self._thread != threading.get_ident():
            raise AgentTaskError('physical presence display belongs to a different thread')

    def open(self, physical: Callable[[], None]) -> None:
        """Connect, require XInput 2 and select raw events for every device on the root window."""
        if self._thread is not None or self._closed:
            raise AgentTaskError('physical presence observer cannot restart')
        self._thread, self._physical = threading.get_ident(), physical
        try:
            self._display = self._factory()
            if not self._display.has_extension('XInputExtension'):
                raise AgentTaskError('X11 physical presence requires the XInput extension')
            if self._display.xinput_query_version().major_version < 2:
                raise AgentTaskError('X11 physical presence requires XInput 2')
            # The public Display answers query_extension; get_extension_major lives on its protocol object.
            self._opcode = self._display.query_extension('XInputExtension').major_opcode
            self._refresh_devices()
            self._display.screen().root.xinput_select_events([(0, _MASK)])
            self._display.flush()
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as error:
            self.close()
            raise AgentTaskError('X11 physical presence observer could not start') from error

    def _refresh_devices(self) -> None:
        slaves = [device for device in self._display.xinput_query_device(0).devices if device.use in _SLAVES]
        self._devices = frozenset(device.deviceid for device in slaves)
        self._injected = frozenset(device.deviceid for device in slaves if 'XTEST' in str(device.name))

    def _raw(self, evtype: int, data: bytes) -> None:
        _device, _time, detail, source, _valuators = _RAW_HEADER.unpack_from(data)
        if source not in self._devices:
            self._refresh_devices()
        if source in self._injected or source not in self._devices:
            return
        if evtype in _RAW_PRESS:
            self._held.add((_RAW_PRESS[evtype], source, detail))
        elif evtype in _RAW_RELEASE:
            self._held.discard((_RAW_RELEASE[evtype], source, detail))
        if self._physical is None:
            raise AgentTaskError('physical presence callback is unavailable')
        self._physical()

    def _event(self, event: Any) -> None:
        if event.type != _GENERIC_EVENT or event.extension != self._opcode:
            return
        if event.evtype == _HIERARCHY_CHANGED:
            self._refresh_devices()
        elif event.evtype in _RAW_EVENTS:
            self._raw(event.evtype, bytes(event.data))

    def _drain(self) -> None:
        for _index in range(_DRAIN_LIMIT):
            if not self._display.pending_events():
                return
            self._event(self._display.next_event())
        if self._display.pending_events():
            raise AgentControlBusy('physical presence input queue is still active')

    def _core_held(self) -> bool:
        keys = self._display.query_keymap()
        pointer = self._display.screen().root.query_pointer()
        return any(keys) or bool(pointer.mask & _BUTTON_MASKS)

    def poll(self, timeout: float) -> tuple[bool, bool]:
        """Drain bounded raw events, then report whether the seat is usable and anything is held."""
        self._owner()
        require_poll_timeout(timeout)
        if self._display is None or self._closed:
            raise AgentTaskError('physical presence observer is unavailable')
        readable, _write, _error = select.select([self._display.fileno()], [], [], timeout)
        if readable or self._display.pending_events():
            self._drain()
        held = bool(self._held) or self._core_held()
        return self._interactive(), held

    def close(self) -> None:
        """Deselect the raw events and close the owned connection."""
        self._owner()
        self._closed = True
        display, self._display = self._display, None
        if display is None:
            return
        try:
            display.screen().root.xinput_select_events([(0, 0)])
            display.flush()
        finally:
            display.close()
