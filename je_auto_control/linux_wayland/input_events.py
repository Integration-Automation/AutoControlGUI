"""Recording on Wayland: what this program did, and what the user did.

X11 lets any client watch every key and click, so "record" there is one
feature. Wayland forbids that on purpose, and the answer is not to find a way
round it — it is to notice that "record" was always two different things:

**What this program executed.** No hook is needed for that; the executor
already knows. :class:`ActionJournal` collects the steps as they run, on every
backend, with nothing read from the desktop at all.

**What the user physically typed and clicked.** That needs the kernel's event
devices, and it is offered here as :class:`PhysicalRecorder` under three
conditions that are the whole design:

* **opt-in, device by device.** Nothing is opened unless the caller names it.
  There is no "all keyboards" default, because the keyboard is also where
  passwords are typed.
* **virtual devices are excluded.** ``ydotool`` injects through
  ``/dev/uinput``, which shows up as one more event device; reading it would
  record this program's own output as though the user had typed it. A device
  whose origin cannot be established is excluded too.
* **no privilege is taken.** Opening a device this user may not read raises
  :class:`InputPermissionError` saying how to grant access. It never retries
  as root and never suggests running the program as root.

The desktop portal's *InputCapture* interface is deliberately not used. It
exists to hand the pointer to another machine once it crosses a screen edge
the compositor chose — the compositor decides when it starts, so it cannot be
a recorder that starts when a script asks.

Pure stdlib and importable everywhere; only :class:`PhysicalRecorder`'s
default device source touches Linux-only calls, and only once started.
"""
from __future__ import annotations

import copy
import os
import struct
import threading
from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03

#: ``BUS_VIRTUAL`` from ``linux/input.h`` — what a uinput device may declare.
BUS_VIRTUAL = 0x06

#: Where the kernel parents every uinput device in sysfs. A Bluetooth
#: keyboard also lives under ``/devices/virtual`` (``…/misc/uhid/…``) and is
#: a real keyboard, which is why the match is this narrow.
_UINPUT_SYSFS = "/devices/virtual/input/"

#: Comma-separated ``/dev/input/event*`` paths the operator opted in to.
RECORD_DEVICES_ENV = "JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES"

#: ``struct input_event`` in this interpreter's native layout.
_EVENT = struct.Struct("@llHHi")

DEFAULT_MAX_EVENTS = 100_000

PERMISSION_RECOVERY = (
    "Give this user read access to the device: add the user to the `input` "
    "group and log in again, or install a udev rule for it. Do not run the "
    "whole program as root for this. To record what this program executes "
    "instead, use ActionJournal — it needs no device at all.")


class InputRecordingError(AutoControlException):
    """Physical input recording could not start, or was misused."""


class InputPermissionError(InputRecordingError):
    """This user may not read an input device; ``recovery`` says what to do."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.recovery = PERMISSION_RECOVERY
        super().__init__(
            f"permission denied reading {path}. {PERMISSION_RECOVERY}")

    @property
    def has_recovery_instruction(self) -> bool:
        """Whether the error tells the operator what to do next."""
        return bool(self.recovery)


@dataclass(frozen=True)
class InputDevice:
    """One kernel event device and where it comes from."""

    path: str
    name: str = ""
    phys: str = ""
    bustype: int = 0
    #: The resolved sysfs path; empty when it could not be read.
    sysfs: str = ""

    @property
    def origin_known(self) -> bool:
        """Whether sysfs said where this device hangs."""
        return bool(self.sysfs)

    @property
    def is_virtual(self) -> bool:
        """Whether this is a uinput device rather than hardware."""
        return (self.bustype == BUS_VIRTUAL
                or _UINPUT_SYSFS in self.sysfs.replace(os.sep, "/") + "/")


@dataclass(frozen=True)
class InputEvent:
    """One evdev event: ``type`` / ``code`` / ``value`` as the kernel has them.

    The same shape is what :mod:`ei_worker` accepts for emission, so a
    recorded stream and a stream to send are one vocabulary.
    """

    type: int
    code: int
    value: int
    time_s: float = 0.0
    device: str = ""


def configured_record_devices(environ: Optional[Mapping[str, str]] = None
                              ) -> Tuple[str, ...]:
    """The device paths the operator opted in to reading, if any."""
    env = environ if environ is not None else os.environ
    raw = env.get(RECORD_DEVICES_ENV) or ""
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def describe_device(path: str, sys_root: str = "/sys/class/input"
                    ) -> InputDevice:
    """Look one ``/dev/input/event*`` node up in sysfs.

    Reads metadata only — the device itself is not opened, so this needs no
    permission and tells nobody anything.
    """
    node = os.path.join(sys_root, os.path.basename(path))
    if not os.path.exists(node):
        return InputDevice(path)
    described = os.path.join(node, "device")
    try:
        bustype = int(_read_text(os.path.join(described, "id", "bustype")), 16)
    except ValueError:
        bustype = 0
    return InputDevice(
        path=path, name=_read_text(os.path.join(described, "name")),
        phys=_read_text(os.path.join(described, "phys")), bustype=bustype,
        sysfs=os.path.realpath(node))


def list_input_devices(sys_root: str = "/sys/class/input",
                       dev_root: str = "/dev/input") -> List[InputDevice]:
    """Every event device sysfs knows about, virtual ones included.

    For choosing what to name in :data:`RECORD_DEVICES_ENV`; check
    :attr:`InputDevice.is_virtual` before recording from one.
    """
    try:
        names = sorted(name for name in os.listdir(sys_root)
                       if name.startswith("event"))
    except OSError:
        return []
    return [describe_device(f"{dev_root.rstrip('/')}/{name}", sys_root)
            for name in names]


def decode_events(data: bytes, device: str = "") -> List[InputEvent]:
    """Split a buffer of ``struct input_event`` records; a tail is dropped."""
    events = []
    for offset in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
        seconds, micros, kind, code, value = _EVENT.unpack_from(data, offset)
        events.append(InputEvent(kind, code, value,
                                 seconds + micros / 1_000_000, device))
    return events


class _EvdevSource:
    """One opened event device, read without blocking past ``timeout``."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))

    def read_events(self, timeout: float) -> List[InputEvent]:
        """Whatever arrived within ``timeout`` seconds, possibly nothing."""
        import select
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            return []
        try:
            data = os.read(self._fd, _EVENT.size * 64)
        except BlockingIOError:
            return []
        return decode_events(data, self.path)

    def close(self) -> None:
        """Release the descriptor; safe to call twice."""
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1


class PhysicalRecorder:
    """Read the user's own input from kernel devices they named.

    ``opener`` turns a device path into something with ``read_events(timeout)``
    and ``close()``; tests pass a fake, the default opens the real node.
    """

    def __init__(self, *, opener: Optional[Callable[[str], Any]] = None,
                 max_events: int = DEFAULT_MAX_EVENTS,
                 poll_s: float = 0.1) -> None:
        self._opener = opener if opener is not None else _EvdevSource
        self._max_events = max(1, int(max_events))
        self._poll_s = max(0.001, float(poll_s))
        self._lock = threading.Lock()
        self._events: List[InputEvent] = []
        self._sources: List[Any] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        #: Devices :meth:`start` refused, and so did not read.
        self.excluded: List[InputDevice] = []
        #: True when the buffer filled and later events were dropped.
        self.truncated = False

    @property
    def is_recording(self) -> bool:
        """Whether devices are open and being read."""
        return self._thread is not None

    def start(self, devices: Sequence[InputDevice]) -> None:
        """Open ``devices`` and begin reading them.

        :param devices: the devices to read — named explicitly; an empty
            sequence is refused rather than read as "everything".
        :raises InputPermissionError: a device is not readable by this user.
        :raises InputRecordingError: nothing was named, nothing named is
            physical, or a recording is already running.
        """
        if self.is_recording:
            raise InputRecordingError("a physical recording is already running")
        if not devices:
            raise InputRecordingError(
                "name the devices to record: physical input recording is "
                "opt-in per device (see list_input_devices() and "
                f"{RECORD_DEVICES_ENV})")
        accepted = [d for d in devices if d.origin_known and not d.is_virtual]
        self.excluded = [d for d in devices if d not in accepted]
        if not accepted:
            raise InputRecordingError(
                "every named device is virtual or of unknown origin, so "
                "there is no physical input to record: "
                + ", ".join(d.path for d in devices))
        self._sources = self._open_all(accepted)
        with self._lock:
            self._events = []
        self.truncated = False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._read_loop, name="wayland-physical-recorder",
            daemon=True)
        self._thread.start()

    def stop(self) -> List[InputEvent]:
        """Stop reading, close every device, and return what was read."""
        thread, self._thread = self._thread, None
        self._stop.set()
        if thread is not None:
            thread.join(timeout=self._poll_s * (len(self._sources) + 1) + 2.0)
        self._close_all(self._sources)
        self._sources = []
        with self._lock:
            events, self._events = self._events, []
        return events

    def _open_all(self, devices: Sequence[InputDevice]) -> List[Any]:
        """Open every device or none: a partial recording misleads."""
        opened: List[Any] = []
        try:
            for device in devices:
                opened.append(self._open_one(device.path))
        except BaseException:
            self._close_all(opened)
            raise
        return opened

    def _open_one(self, path: str) -> Any:
        try:
            return self._opener(path)
        except PermissionError as error:
            raise InputPermissionError(path) from error
        except OSError as error:
            raise InputRecordingError(
                f"could not open {path}: {error}") from error

    @staticmethod
    def _close_all(sources: Sequence[Any]) -> None:
        for source in sources:
            try:
                source.close()
            except OSError:
                pass

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            for source in self._sources:
                try:
                    events = source.read_events(self._poll_s)
                except OSError:
                    # The device went away (unplugged). What was read stands.
                    self._stop.set()
                    return
                self._keep(events)

    def _keep(self, events: Sequence[InputEvent]) -> None:
        if not events:
            return
        with self._lock:
            room = self._max_events - len(self._events)
            if room < len(events):
                self.truncated = True
            self._events.extend(events[:max(0, room)])


class ActionJournal:
    """The steps this program executed, collected without any input hook.

    Hand :meth:`note` to the executor as its ``step_callback`` — or call
    :meth:`run` — and every top-level action is appended as it starts. It
    works identically on every backend because it reads nothing from the
    desktop: it is the program writing down what it was told to do.

    Steps are kept verbatim so they can be replayed, which means anything
    secret in an action's arguments is in here too. Treat a journal like the
    action file it came from.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._steps: List[Any] = []

    def note(self, action: Any) -> None:
        """Record one action; a copy, so later mutation cannot rewrite it."""
        with self._lock:
            self._steps.append(copy.deepcopy(action))

    @property
    def steps(self) -> List[Any]:
        """Every step noted so far, oldest first."""
        with self._lock:
            return copy.deepcopy(self._steps)

    def clear(self) -> None:
        """Forget every step."""
        with self._lock:
            self._steps = []

    def run(self, action_list: Any, *,
            execute: Optional[Callable[..., Any]] = None,
            **options: Any) -> Any:
        """Execute ``action_list`` and journal each step as it starts.

        :param execute: the executor entry point; the framework's own
            ``executor.execute_action`` when omitted.
        :param options: passed through (``raise_on_error``, ``dry_run``).
        """
        if execute is None:
            from je_auto_control.utils.executor.action_executor import executor
            execute = executor.execute_action
        return execute(action_list, step_callback=self.note, **options)


__all__ = [
    "ActionJournal", "BUS_VIRTUAL", "DEFAULT_MAX_EVENTS", "EV_ABS", "EV_KEY",
    "EV_REL", "EV_SYN", "InputDevice", "InputEvent", "InputPermissionError",
    "InputRecordingError", "PERMISSION_RECOVERY", "PhysicalRecorder",
    "RECORD_DEVICES_ENV", "configured_record_devices", "decode_events",
    "describe_device", "list_input_devices",
]
