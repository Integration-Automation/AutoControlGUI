"""Owned raw physical recording and portal stop services with independent GUI lifetimes."""
from __future__ import annotations

from dataclasses import asdict
import threading
from typing import Any, Callable, Optional

from je_auto_control.linux_wayland.global_shortcuts import ShortcutUnavailable, StopShortcutSession
from je_auto_control.linux_wayland.input_events import (
    InputDevice, MAX_DEVICES, PhysicalRecorder, RecordingUnavailable,
)
from je_auto_control.utils.exception.exceptions import AutoControlException


def _stop_native_control() -> None:
    # pylint: disable-next=import-outside-toplevel  # reason: constructing a session must not load a native backend
    from je_auto_control.linux_wayland.libei import stop_input_control
    stop_input_control()


class WaylandInputSession:
    """Own recording and a stop grant; raw events never become replay coordinates.

    Construction has no I/O or consent side effects. GUI panels create their
    own instance; command adapters share the script default. ``stop_event`` is
    caller-readable cooperative cancellation evidence, not a process interrupt.
    Closing permanently rejects new starts and attempts both owned cleanups;
    failed cleanup remains retryable. No device ACL is modified.
    """

    def __init__(self, *, _recorder: Optional[PhysicalRecorder] = None,
                 _shortcut: Optional[StopShortcutSession] = None,
                 _stop_control: Optional[Callable[[], None]] = None) -> None:
        self._recorder = _recorder if _recorder is not None else PhysicalRecorder()
        self._shortcut = _shortcut if _shortcut is not None else StopShortcutSession()
        self._stop_control = _stop_control if _stop_control is not None else _stop_native_control
        self.stop_event = threading.Event()
        self._lock = threading.RLock()
        self._closed = False

    def _require_open(self) -> None:
        if self._closed:
            raise RecordingUnavailable('this input session is closed; create a new owner')

    def start_physical(self, devices: list[str]) -> dict[str, Any]:
        """Explicitly select physical nodes; use their existing read permission."""
        if not isinstance(devices, list) or not 1 <= len(devices) <= MAX_DEVICES:
            raise RecordingUnavailable(f'devices must be a list of one to {MAX_DEVICES} paths')
        selected = [InputDevice(path) for path in devices]
        with self._lock:
            self._require_open()
            self._recorder.start(selected)
            return self.status()

    def stop_physical(self) -> list[dict[str, Any]]:
        """Join capture and return raw device events, without replay conversion."""
        with self._lock:
            return [asdict(event) for event in self._recorder.stop()]

    def _stopped(self) -> None:
        self.stop_event.set()
        self._stop_control()

    def start_shortcut(self, preferred_trigger: str = 'F7') -> dict[str, Any]:
        """Explicitly request asynchronous consent for stopping native input control."""
        with self._lock:
            self._require_open()
            was_stopped = self.stop_event.is_set()
            self.stop_event.clear()
            try:
                self._shortcut.start(self._stopped, preferred_trigger=preferred_trigger)
            except ShortcutUnavailable:
                if was_stopped:
                    self.stop_event.set()
                raise
            return self.status()

    def stop_shortcut(self) -> dict[str, Any]:
        """Cancel a pending request or release only this owner's stop grant."""
        with self._lock:
            self._shortcut.close()
            return self.status()

    def status(self) -> dict[str, Any]:
        """Read local lifecycle evidence; never probe, capture or request consent."""
        with self._lock:
            error = self._recorder.error
            physical_state = error.state if error else ('available' if self._recorder.running else 'closed')
            return {'physical': {'state': physical_state, 'devices': list(self._recorder.devices),
                                 'error': str(error) if error else ''},
                    'shortcut': {'state': self._shortcut.state,
                                 'trigger_description': self._shortcut.trigger_description,
                                 'error': str(self._shortcut.error) if self._shortcut.error else ''},
                    'stop_requested': self.stop_event.is_set(), 'closed': self._closed}

    def close(self) -> None:
        """Reject new work, attempt both owned cleanups and retain retryable failure."""
        with self._lock:
            self._closed = True
            self.stop_event.set()
            failures: list[AutoControlException] = []
            for cleanup in (self._shortcut.close, self._recorder.stop):
                try:
                    cleanup()
                except (RecordingUnavailable, ShortcutUnavailable) as failure:
                    failures.append(failure)
            if failures:
                raise failures[0]


_DEFAULT_LOCK = threading.Lock()
_SCRIPT_OWNERS: dict[str, WaylandInputSession] = {}


def _script_session() -> WaylandInputSession:
    with _DEFAULT_LOCK:
        if 'default' not in _SCRIPT_OWNERS:
            _SCRIPT_OWNERS['default'] = WaylandInputSession()
        return _SCRIPT_OWNERS['default']


def start_physical_recording(devices: list[str]) -> dict[str, Any]:
    """Start the script-owned raw recorder for explicitly selected physical Linux nodes."""
    return _script_session().start_physical(devices)


def stop_physical_recording() -> list[dict[str, Any]]:
    """Stop the script-owned recorder and return raw events, not replay actions."""
    return _script_session().stop_physical()


def start_wayland_stop_shortcut(preferred_trigger: str = 'F7') -> dict[str, Any]:
    """Explicitly request a script-owned portal shortcut to stop native input control."""
    return _script_session().start_shortcut(preferred_trigger)


def stop_wayland_stop_shortcut() -> dict[str, Any]:
    """Cancel or release the script-owned stop registration without touching GUI grants."""
    return _script_session().stop_shortcut()


def wayland_input_status() -> dict[str, Any]:
    """Read script-owned recording/stop evidence without device I/O or authorization."""
    return _script_session().status()
