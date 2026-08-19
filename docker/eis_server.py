"""A minimal EIS server, bound to the real ``libeis.so`` with ctypes.

AutoControl's libei sender had been verified as far as a peer-less container
can go: every prototype resolves, every call behaves, and the whole
fail-closed chain runs. What could not be checked without something that
speaks the protocol was the half where a wrong value is silently accepted —
the capability and event-type enums, the variadic
``ei_seat_bind_capabilities`` marshalling, seat capability grants, device
pause/resume, and whether ``start_emulating`` → event → ``frame`` actually
puts anything on the wire.

``libeis`` is the server side of the same protocol and Debian packages it
(``libeis1`` / ``libeis-dev``), so that peer can just be built here: this
module runs a real EIS implementation on a Unix socket, in a thread, and
records everything a client does to it. No compositor, no desktop session, no
GNOME VM — the two libraries talk to each other and the recording is the
evidence.

It is a verification fixture, not shipped library code, which is why it lives
under ``docker/`` next to the image that runs it.
"""
from __future__ import annotations

import ctypes
import select
import threading
from typing import Dict, List, Optional, Sequence, Set, Tuple

from je_auto_control.linux_wayland._ctypes_bind import BoundSymbols, bind

_LIBRARY_CANDIDATES = ("eis", "libeis", "libeis.so.1", "libeis.so.0")

# enum eis_device_capability — the server side of the same bitmask libei.py
# declares. Deliberately re-declared from libeis.h rather than imported from
# libei.py: if both sides read the same wrong constant the test passes while
# the protocol is broken, and this file exists to catch exactly that.
EIS_DEVICE_CAP_POINTER = 1 << 0
EIS_DEVICE_CAP_POINTER_ABSOLUTE = 1 << 1
EIS_DEVICE_CAP_KEYBOARD = 1 << 2
EIS_DEVICE_CAP_TOUCH = 1 << 3
EIS_DEVICE_CAP_SCROLL = 1 << 4
EIS_DEVICE_CAP_BUTTON = 1 << 5

CAPABILITY_NAMES = {
    EIS_DEVICE_CAP_POINTER: "POINTER",
    EIS_DEVICE_CAP_POINTER_ABSOLUTE: "POINTER_ABSOLUTE",
    EIS_DEVICE_CAP_KEYBOARD: "KEYBOARD",
    EIS_DEVICE_CAP_TOUCH: "TOUCH",
    EIS_DEVICE_CAP_SCROLL: "SCROLL",
    EIS_DEVICE_CAP_BUTTON: "BUTTON",
}

# enum eis_event_type, from libeis.h.
EIS_EVENT_CLIENT_CONNECT = 1
EIS_EVENT_CLIENT_DISCONNECT = 2
EIS_EVENT_SEAT_BIND = 3
EIS_EVENT_DEVICE_CLOSED = 4
EIS_EVENT_FRAME = 100
EIS_EVENT_DEVICE_START_EMULATING = 200
EIS_EVENT_DEVICE_STOP_EMULATING = 201
EIS_EVENT_POINTER_MOTION = 300
EIS_EVENT_POINTER_MOTION_ABSOLUTE = 400
EIS_EVENT_BUTTON_BUTTON = 500
EIS_EVENT_SCROLL_DISCRETE = 603
EIS_EVENT_KEYBOARD_KEY = 700

#: What this server offers a seat. Wider than AutoControl asks for on
#: purpose — a client that binds a capability it never requested, or misses
#: one it did, then shows up in ``bound_capabilities``.
OFFERED_CAPABILITIES = (
    EIS_DEVICE_CAP_POINTER, EIS_DEVICE_CAP_POINTER_ABSOLUTE,
    EIS_DEVICE_CAP_KEYBOARD, EIS_DEVICE_CAP_TOUCH,
    EIS_DEVICE_CAP_SCROLL, EIS_DEVICE_CAP_BUTTON,
)

#: The absolute pointer needs a region or the compositor has no coordinate
#: space to place motion in.
REGION_SIZE = (1920, 1080)

#: Default shape of that space: one region at the origin, as ``((x, y),
#: (width, height))``. ``regions=`` overrides it, which is how the offset
#: layout that a monitor left of the primary produces gets exercised.
DEFAULT_REGIONS = (((0, 0), REGION_SIZE),)

_VOID = ctypes.c_void_p
_U32 = ctypes.c_uint32
_PROTOTYPES = (
    ("eis_new", _VOID, (_VOID,)),
    ("eis_unref", _VOID, (_VOID,)),
    ("eis_setup_backend_socket", ctypes.c_int, (_VOID, ctypes.c_char_p)),
    ("eis_get_fd", ctypes.c_int, (_VOID,)),
    ("eis_dispatch", None, (_VOID,)),
    ("eis_get_event", _VOID, (_VOID,)),
    ("eis_event_unref", _VOID, (_VOID,)),
    ("eis_event_get_type", ctypes.c_int, (_VOID,)),
    ("eis_event_get_client", _VOID, (_VOID,)),
    ("eis_event_get_seat", _VOID, (_VOID,)),
    ("eis_event_get_device", _VOID, (_VOID,)),
    ("eis_event_seat_has_capability", ctypes.c_bool, (_VOID, ctypes.c_int)),
    ("eis_client_connect", None, (_VOID,)),
    ("eis_client_disconnect", None, (_VOID,)),
    ("eis_client_is_sender", ctypes.c_bool, (_VOID,)),
    ("eis_client_get_name", ctypes.c_char_p, (_VOID,)),
    ("eis_client_new_seat", _VOID, (_VOID, ctypes.c_char_p)),
    ("eis_seat_configure_capability", None, (_VOID, ctypes.c_int)),
    ("eis_seat_add", None, (_VOID,)),
    ("eis_seat_new_device", _VOID, (_VOID,)),
    ("eis_device_configure_name", None, (_VOID, ctypes.c_char_p)),
    ("eis_device_configure_capability", None, (_VOID, ctypes.c_int)),
    ("eis_device_new_region", _VOID, (_VOID,)),
    ("eis_region_set_size", None, (_VOID, _U32, _U32)),
    ("eis_region_set_offset", None, (_VOID, _U32, _U32)),
    ("eis_region_add", None, (_VOID,)),
    ("eis_device_add", None, (_VOID,)),
    ("eis_device_remove", None, (_VOID,)),
    ("eis_device_pause", None, (_VOID,)),
    ("eis_device_resume", None, (_VOID,)),
    ("eis_device_get_name", ctypes.c_char_p, (_VOID,)),
    ("eis_event_emulating_get_sequence", _U32, (_VOID,)),
    ("eis_event_keyboard_get_key", _U32, (_VOID,)),
    ("eis_event_keyboard_get_key_is_press", ctypes.c_bool, (_VOID,)),
    ("eis_event_pointer_get_absolute_x", ctypes.c_double, (_VOID,)),
    ("eis_event_pointer_get_absolute_y", ctypes.c_double, (_VOID,)),
    ("eis_event_button_get_button", _U32, (_VOID,)),
    ("eis_event_button_get_is_press", ctypes.c_bool, (_VOID,)),
    ("eis_event_scroll_get_discrete_dx", ctypes.c_int32, (_VOID,)),
    ("eis_event_scroll_get_discrete_dy", ctypes.c_int32, (_VOID,)),
)


class EisUnavailable(RuntimeError):
    """libeis is missing, or a server cannot be brought up here."""


def load_symbols() -> Optional[BoundSymbols]:
    """Resolve every libeis entry point, or None if one is missing."""
    return bind(_LIBRARY_CANDIDATES, _PROTOTYPES)


class Recording:
    """Everything one client did, as the server saw it happen."""

    def __init__(self) -> None:
        self.clients: List[str] = []
        self.sender_flags: List[bool] = []
        self.bound_capabilities: Set[int] = set()
        self.seat_binds = 0
        self.devices: List[str] = []
        self.emulating_sequences: List[Tuple[str, int]] = []
        self.stopped_emulating = 0
        self.frames = 0
        self.keys: List[Tuple[int, bool]] = []
        self.absolute_motions: List[Tuple[float, float]] = []
        self.buttons: List[Tuple[int, bool]] = []
        self.scrolls: List[Tuple[int, int]] = []
        self.disconnects = 0
        #: Device labels this server asked to pause, for diagnosis.
        self.paused: List[str] = []
        #: ``(event type, device name)`` for everything, in arrival order —
        #: what a failing check needs to explain itself.
        self.event_log: List[Tuple[int, str]] = []

    def capability_names(self) -> List[str]:
        return sorted(CAPABILITY_NAMES.get(cap, str(cap))
                      for cap in self.bound_capabilities)


class RecordingEisServer:
    """A real EIS server that grants a seat and records what arrives.

    Runs its whole libeis context on one background thread: libeis is not
    thread-safe, and the client under test drives the main thread, so the two
    contexts never share one.
    """

    def __init__(self, socket_path: str,
                 *, symbols: Optional[BoundSymbols] = None,
                 regions: Optional[Sequence[Tuple[Tuple[int, int],
                                                  Tuple[int, int]]]] = None,
                 ) -> None:
        self.socket_path = socket_path
        self.recording = Recording()
        self.regions = tuple(DEFAULT_REGIONS if regions is None else regions)
        self._symbols = symbols if symbols is not None else load_symbols()
        self._eis: Optional[int] = None
        self._devices: Dict[str, int] = {}
        self._seat_devices_created = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[BaseException] = None
        #: Work handed to the serving thread; a list because append and pop
        #: are atomic and this needs no more locking than that.
        self._pending: List[tuple] = []

    # --- lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Bring the server up and begin answering clients."""
        if self._symbols is None:
            raise EisUnavailable("libeis.so.* not found on the loader path")
        context = self._symbols.eis_new(None)
        if not context:
            raise EisUnavailable("eis_new returned NULL")
        self._eis = context
        code = self._symbols.eis_setup_backend_socket(
            context, self.socket_path.encode("utf-8"))
        if code != 0:
            raise EisUnavailable(f"eis_setup_backend_socket returned {code}")
        self._thread = threading.Thread(target=self._serve, daemon=True,
                                        name="eis-server")
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Ask the loop to finish and wait for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    @property
    def error(self) -> Optional[BaseException]:
        """Whatever took the serving thread down, if anything did."""
        return self._error

    def pause_devices(self) -> None:
        """Suspend every device, so a client must stop emulating."""
        self._on_server_thread(self._pause_all)

    def _pause_all(self) -> None:
        for label, device in self._devices.items():
            name = self._symbols.eis_device_get_name(device)
            self.recording.paused.append(
                f"{label}={name.decode() if name else '<gone>'}")
            self._symbols.eis_device_pause(device)
        # libeis buffers outgoing messages; a dispatch is what puts them on
        # the wire, and nothing else here would trigger one while the client
        # is only *sending*.
        self._symbols.eis_dispatch(self._eis)

    def resume_devices(self) -> None:
        """Resume every device, so a client may emulate again."""
        self._on_server_thread(
            lambda: [self._symbols.eis_device_resume(device)
                     for device in self._devices.values()])

    def _on_server_thread(self, action, timeout: float = 2.0) -> None:
        """Run ``action`` on the serving thread and wait for it.

        libeis is not thread-safe, and every other call into this context
        already happens on that thread. Pausing a device from the caller's
        thread appeared to work and then simply never reached the client —
        which reads exactly like the client ignoring the event, so it is
        worth not being able to make that mistake.
        """
        done = threading.Event()
        self._pending.append((action, done))
        if not done.wait(timeout):
            raise EisUnavailable("the server thread did not run a queued action")

    # --- event loop -------------------------------------------------------

    def _serve(self) -> None:
        try:
            poll_fd = int(self._symbols.eis_get_fd(self._eis))
            while not self._stop.is_set():
                self._run_pending()
                ready, _, _ = select.select([poll_fd], [], [], 0.05)
                if not ready:
                    continue
                self._symbols.eis_dispatch(self._eis)
                self._drain()
        except BaseException as error:  # noqa: BLE001  # reason: a fixture thread must report, not vanish
            self._error = error

    def _run_pending(self) -> None:
        while self._pending:
            action, done = self._pending.pop(0)
            try:
                action()
            finally:
                done.set()

    def _drain(self) -> None:
        while True:
            event = self._symbols.eis_get_event(self._eis)
            if not event:
                return
            try:
                self._on_event(event)
            finally:
                self._symbols.eis_event_unref(event)

    def _on_event(self, event: int) -> None:
        event_type = int(self._symbols.eis_event_get_type(event))
        self.recording.event_log.append((event_type, self._device_name(event)))
        handler = _HANDLERS.get(event_type)
        if handler is not None:
            handler(self, event)

    def _device_name(self, event: int) -> str:
        """The device an event belongs to, for the log. ``''`` when it has none."""
        device = self._symbols.eis_event_get_device(event)
        if not device:
            return ""
        name = self._symbols.eis_device_get_name(device)
        return name.decode("utf-8", "replace") if name else f"<{device:#x}>"

    # --- handlers ---------------------------------------------------------

    def _on_client_connect(self, event: int) -> None:
        """Accept a sender client and offer it one fully-capable seat."""
        client = self._symbols.eis_event_get_client(event)
        name = self._symbols.eis_client_get_name(client)
        self.recording.clients.append(
            name.decode("utf-8", "replace") if name else "<unnamed>")
        self.recording.sender_flags.append(
            bool(self._symbols.eis_client_is_sender(client)))
        self._symbols.eis_client_connect(client)
        seat = self._symbols.eis_client_new_seat(client, b"autocontrol-seat")
        for capability in OFFERED_CAPABILITIES:
            self._symbols.eis_seat_configure_capability(seat, capability)
        self._symbols.eis_seat_add(seat)

    def _on_seat_bind(self, event: int) -> None:
        """Record what the client asked this seat for, then hand it devices.

        This is the whole point of the fixture. ``eis_event_seat_has_capability``
        reads back what the client's variadic ``ei_seat_bind_capabilities``
        actually put on the wire, so a wrong enum value or a mis-marshalled
        argument shows up as a missing or unexpected capability rather than as
        a handshake that quietly never completes.
        """
        self.recording.seat_binds += 1
        seat = self._symbols.eis_event_get_seat(event)
        bound = {cap for cap in OFFERED_CAPABILITIES
                 if self._symbols.eis_event_seat_has_capability(event, cap)}
        self.recording.bound_capabilities |= bound
        if not bound or self._seat_devices_created:
            return
        self._seat_devices_created = True
        if EIS_DEVICE_CAP_KEYBOARD in bound:
            self._add_device("keyboard", seat, (EIS_DEVICE_CAP_KEYBOARD,))
        pointer_caps = tuple(
            cap for cap in (EIS_DEVICE_CAP_POINTER_ABSOLUTE,
                            EIS_DEVICE_CAP_BUTTON, EIS_DEVICE_CAP_SCROLL)
            if cap in bound)
        if pointer_caps:
            self._add_device("pointer", seat, pointer_caps, region=True)

    def _add_device(self, label: str, seat: int, capabilities: tuple,
                    *, region: bool = False) -> None:
        device = self._symbols.eis_seat_new_device(seat)
        self._symbols.eis_device_configure_name(
            device, f"autocontrol-{label}".encode("utf-8"))
        for capability in capabilities:
            self._symbols.eis_device_configure_capability(device, capability)
        if region:
            for offset, size in self.regions:
                shape = self._symbols.eis_device_new_region(device)
                self._symbols.eis_region_set_offset(shape, *offset)
                self._symbols.eis_region_set_size(shape, *size)
                self._symbols.eis_region_add(shape)
        self._symbols.eis_device_add(device)
        self._symbols.eis_device_resume(device)
        self._devices[label] = device
        self.recording.devices.append(label)

    def _on_start_emulating(self, event: int) -> None:
        device = self._symbols.eis_event_get_device(event)
        name = self._symbols.eis_device_get_name(device) if device else None
        self.recording.emulating_sequences.append((
            name.decode("utf-8", "replace") if name else "<unnamed>",
            int(self._symbols.eis_event_emulating_get_sequence(event)),
        ))

    def _on_stop_emulating(self, _event: int) -> None:
        self.recording.stopped_emulating += 1

    def _on_frame(self, _event: int) -> None:
        self.recording.frames += 1

    def _on_keyboard_key(self, event: int) -> None:
        self.recording.keys.append((
            int(self._symbols.eis_event_keyboard_get_key(event)),
            bool(self._symbols.eis_event_keyboard_get_key_is_press(event)),
        ))

    def _on_absolute_motion(self, event: int) -> None:
        self.recording.absolute_motions.append((
            float(self._symbols.eis_event_pointer_get_absolute_x(event)),
            float(self._symbols.eis_event_pointer_get_absolute_y(event)),
        ))

    def _on_button(self, event: int) -> None:
        self.recording.buttons.append((
            int(self._symbols.eis_event_button_get_button(event)),
            bool(self._symbols.eis_event_button_get_is_press(event)),
        ))

    def _on_scroll_discrete(self, event: int) -> None:
        self.recording.scrolls.append((
            int(self._symbols.eis_event_scroll_get_discrete_dx(event)),
            int(self._symbols.eis_event_scroll_get_discrete_dy(event)),
        ))

    def _on_client_disconnect(self, _event: int) -> None:
        self.recording.disconnects += 1


_HANDLERS = {
    EIS_EVENT_CLIENT_CONNECT: RecordingEisServer._on_client_connect,
    EIS_EVENT_CLIENT_DISCONNECT: RecordingEisServer._on_client_disconnect,
    EIS_EVENT_SEAT_BIND: RecordingEisServer._on_seat_bind,
    EIS_EVENT_DEVICE_START_EMULATING: RecordingEisServer._on_start_emulating,
    EIS_EVENT_DEVICE_STOP_EMULATING: RecordingEisServer._on_stop_emulating,
    EIS_EVENT_FRAME: RecordingEisServer._on_frame,
    EIS_EVENT_KEYBOARD_KEY: RecordingEisServer._on_keyboard_key,
    EIS_EVENT_POINTER_MOTION_ABSOLUTE: RecordingEisServer._on_absolute_motion,
    EIS_EVENT_BUTTON_BUTTON: RecordingEisServer._on_button,
    EIS_EVENT_SCROLL_DISCRETE: RecordingEisServer._on_scroll_discrete,
}


__all__ = [
    "CAPABILITY_NAMES", "EisUnavailable", "OFFERED_CAPABILITIES",
    "DEFAULT_REGIONS", "REGION_SIZE",
    "Recording", "RecordingEisServer", "load_symbols",
    "EIS_DEVICE_CAP_POINTER", "EIS_DEVICE_CAP_POINTER_ABSOLUTE",
    "EIS_DEVICE_CAP_KEYBOARD", "EIS_DEVICE_CAP_TOUCH",
    "EIS_DEVICE_CAP_SCROLL", "EIS_DEVICE_CAP_BUTTON",
]
