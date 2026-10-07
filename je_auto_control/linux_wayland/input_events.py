"""Opt-in physical Linux event capture, independent of synthetic desktop input.

Only explicitly supplied /dev/input/event nodes are opened. The default reader
checks kernel sysfs identity and excludes virtual devices, including uinput.
Events retain device units; relative motion is not a desktop coordinate and
must not be silently converted into a replay position. No ACLs are changed.
"""
from __future__ import annotations

import atexit
import contextlib
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import select
import stat
import struct
import sys
import threading
from typing import Optional, Protocol, Sequence

from je_auto_control.utils.exception.exceptions import AutoControlException


# Linux input_event uses native long timeval members and native endian values.
EVENT_STRUCT = struct.Struct('@llHHi')
MAX_DEVICES = 16
MAX_EVENTS = 20_000
_READ_BYTES = EVENT_STRUCT.size * 128
_POLL_SECONDS = 0.05
_JOIN_SECONDS = 2.0


class RecordingUnavailable(AutoControlException, NotImplementedError):
    """Physical input cannot be recorded with the selected source/permissions."""

    capability = 'physical_recording'
    has_recovery_instruction = True

    def __init__(self, reason: str, *, state: str = 'unsupported') -> None:
        self.state = state
        self.reason = reason
        self.recovery = ('Select a physical /dev/input/event node with an existing read ACL, '
                         'or ask the device administrator for access to that specific node. '
                         'Executor action journals need no global input hook; use GUI Stop for control.')
        super().__init__(f'{reason}. {self.recovery}')


@dataclass(frozen=True)
class InputDevice:
    """One explicitly chosen event node; identity is verified when it is opened."""

    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path or '\x00' in self.path:
            raise RecordingUnavailable('input device path must be nonempty text without NUL')


@dataclass(frozen=True)
class InputEvent:
    """A raw physical event with kernel timestamp and unchanged device units."""

    device: str
    timestamp_ns: int
    event_type: int
    code: int
    value: int


class _Reader(Protocol):
    """The nonblocking, bounded device I/O seam used by native and fake readers."""

    def open(self, device: InputDevice) -> Optional[int]:
        """Open a physical source; return None for virtual sources."""
        raise NotImplementedError

    def poll(self, handles: Sequence[int], timeout: float) -> list[int]:
        """Return readable sources within the bounded wait."""
        raise NotImplementedError

    def read(self, handle: int) -> bytes:
        """Read at most one bounded batch without blocking."""
        raise NotImplementedError

    def close(self, handle: int) -> None:
        """Release exactly one owned source."""
        raise NotImplementedError


class _LinuxReader:
    """Read existing devices without grabbing them or changing permissions."""

    @staticmethod
    def open(device: InputDevice) -> Optional[int]:
        """Verify identity and open an existing physical source without a grab."""
        if sys.platform != 'linux':
            raise RecordingUnavailable('physical event capture requires Linux')
        path = Path(device.path).resolve(strict=True)
        if path.parent != Path('/dev/input') or re.fullmatch(r'event\d+', path.name) is None:
            raise RecordingUnavailable('choose a /dev/input/event node or a by-id link to one')
        kernel_path = (Path('/sys/class/input') / path.name / 'device').resolve(strict=True)
        if 'virtual' in kernel_path.parts:
            return None
        if not kernel_path.is_relative_to('/sys/devices'):
            raise RecordingUnavailable('input source has no verifiable kernel device identity')
        before = path.stat()
        # pylint: disable-next=no-member  # reason: Linux-only flags guarded above; Windows host lacks them
        handle = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            after = os.fstat(handle)
            def identity(value: os.stat_result) -> tuple[int, int, int]:
                return value.st_dev, value.st_ino, value.st_rdev
            if (not stat.S_ISCHR(after.st_mode) or identity(before) != identity(after)
                    or (Path('/sys/class/input') / path.name / 'device').resolve(strict=True) != kernel_path):
                raise RecordingUnavailable('input device changed while opening it; select it again')
            return handle
        except BaseException:  # reason: an opened fd must be released even when startup is cancelled
            os.close(handle)
            raise

    @staticmethod
    def poll(handles: Sequence[int], timeout: float) -> list[int]:
        """Wait only for these owned descriptors, without a global hook."""
        ready, _, _ = select.select(list(handles), [], [], timeout)
        return ready

    @staticmethod
    def read(handle: int) -> bytes:
        """Read one bounded native event batch from a nonblocking fd."""
        return os.read(handle, _READ_BYTES)

    @staticmethod
    def close(handle: int) -> None:
        """Release the recorder's descriptor."""
        os.close(handle)


@dataclass
class _RecordingRun:
    thread: Optional[threading.Thread] = None
    events: list[InputEvent] = field(default_factory=list)
    failure: Optional[RecordingUnavailable] = None
    devices: tuple[str, ...] = ()


class PhysicalRecorder:
    """Capture explicitly selected physical sources with bounded storage/stop.

    ``stop`` returns raw events, not cursor coordinates or replay commands.
    Permission loss, queue drops, device removal and capacity exhaustion fail
    the recording rather than returning a silently incomplete successful list.
    The private I/O seam allows tests without opening a user's input devices.
    """

    def __init__(self, *, _io: Optional[_Reader] = None) -> None:
        self._io: _Reader = _io if _io is not None else _LinuxReader()
        self._operation = threading.Lock()
        self._stop = threading.Event()
        self._live = _RecordingRun()

    @property
    def running(self) -> bool:
        """Whether the capture worker is alive and has not been asked to stop."""
        with self._operation:
            return self._live.thread is not None and self._live.thread.is_alive() and not self._stop.is_set()

    @property
    def devices(self) -> tuple[str, ...]:
        """Return only selected physical sources, excluding rejected virtual nodes."""
        with self._operation:
            return self._live.devices

    @property
    def error(self) -> Optional[RecordingUnavailable]:
        """Return an asynchronous capture failure without consuming its events."""
        with self._operation:
            return self._live.failure

    def start(self, devices: Sequence[InputDevice]) -> None:
        """Start capture after all source identities and read permissions pass."""
        devices = tuple(devices)
        with self._operation:
            if self._live.thread is not None:
                raise RecordingUnavailable('stop the previous physical recording before starting another')
            if not devices or len(devices) > MAX_DEVICES:
                raise RecordingUnavailable(f'choose between one and {MAX_DEVICES} physical input devices')
            if len({os.path.realpath(device.path) for device in devices}) != len(devices):
                raise RecordingUnavailable('select each physical device once; duplicate sources repeat events')
            handles = self._open_sources(devices)
            self._live = _RecordingRun(devices=tuple(device.path for device in handles.values()))
            self._stop.clear()
            worker = threading.Thread(target=self._collect, args=(handles,),
                                      name='autocontrol-physical-recorder', daemon=True)
            try:
                worker.start()
            except BaseException:  # reason: startup cancellation cannot leave opened physical fds behind
                self._close_sources(handles)
                raise
            self._live.thread = worker
            atexit.register(self.close)

    def _open_sources(self, devices: Sequence[InputDevice]) -> dict[int, InputDevice]:
        handles: dict[int, InputDevice] = {}
        try:
            for device in devices:
                handle = self._io.open(device)
                if handle is not None:
                    handles[handle] = device
            if not handles:
                raise RecordingUnavailable('selected sources are virtual; select physical input devices')
            return handles
        except OSError as failure:
            self._close_sources(handles)
            raise self._io_failure(failure) from failure
        except BaseException:  # reason: partial startup must close every fd before propagating cancellation
            self._close_sources(handles)
            raise

    @staticmethod
    def _io_failure(failure: OSError) -> RecordingUnavailable:
        return RecordingUnavailable(f'cannot read the selected physical input device: {failure}',
                                    state='needs_permission' if isinstance(failure, PermissionError) else 'unsupported')

    def _close_sources(self, handles: dict[int, InputDevice]) -> None:
        for handle in handles:
            try:
                self._io.close(handle)
            except OSError as failure:
                if self._live.failure is None:
                    self._live.failure = self._io_failure(failure)

    def _collect(self, handles: dict[int, InputDevice]) -> None:
        pending = {handle: b'' for handle in handles}
        try:
            while not self._stop.is_set():
                for handle in self._io.poll(list(handles), _POLL_SECONDS):
                    pending[handle] = self._consume(handles[handle], pending[handle], self._io.read(handle))
            if any(pending.values()):
                raise RecordingUnavailable('physical input ended with an incomplete event; restart recording')
        except OSError as failure:
            self._live.failure = self._io_failure(failure)
        except RecordingUnavailable as failure:
            self._live.failure = failure
        # pylint: disable-next=broad-exception-caught  # reason: arbitrary reader failures must fail closed in this thread
        except Exception as failure:  # reason: a reader invariant failure cannot report a successful partial recording
            self._live.failure = RecordingUnavailable(f'physical input reader failed: {type(failure).__name__}')
        finally:
            self._close_sources(handles)

    def _consume(self, device: InputDevice, pending: bytes, payload: bytes) -> bytes:
        if not payload:
            raise RecordingUnavailable('physical input device was removed or reached EOF')
        if len(payload) > _READ_BYTES:
            raise RecordingUnavailable('physical input reader exceeded its batch budget')
        data = pending + payload
        complete = len(data) - len(data) % EVENT_STRUCT.size
        for seconds, micros, kind, code, value in EVENT_STRUCT.iter_unpack(data[:complete]):
            if kind == 0 and code == 3:
                raise RecordingUnavailable('physical input events were dropped; restart capture to resynchronize')
            if len(self._live.events) >= MAX_EVENTS:
                raise RecordingUnavailable('physical recording reached its event budget')
            if not 0 <= micros < 1_000_000:
                raise RecordingUnavailable('physical input returned an invalid timestamp')
            timestamp = seconds * 1_000_000_000 + micros * 1000
            self._live.events.append(InputEvent(device.path, timestamp, kind, code, value))
        return data[complete:]

    def stop(self) -> list[InputEvent]:
        """Stop, join and release all sources; reject any incomplete recording."""
        with self._operation:
            if self._live.thread is None:
                return []
            self._stop.set()
            self._live.thread.join(_JOIN_SECONDS)
            if self._live.thread.is_alive():
                raise RecordingUnavailable('physical reader has not stopped; retry cleanup before starting another')
            self._live.thread = None
            atexit.unregister(self.close)
            captured, self._live.events = self._live.events, []
            if self._live.failure is not None:
                raise self._live.failure
            return captured

    def close(self) -> None:
        """Release resources at shutdown; explicit stop retains failure reporting."""
        with contextlib.suppress(RecordingUnavailable):
            self.stop()
