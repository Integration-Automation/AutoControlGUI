"""ctypes binding for libei — Wayland's input-emulation protocol.

libei is not a "call a function and a key is pressed" library. A sender has
to complete a handshake before it may emit anything:

1. open a backend — an EIS **file descriptor** from the desktop portal
   (:mod:`oeffis`), or a socket path where a compositor exposes one;
2. pump ``ei_dispatch`` / ``ei_get_event`` and answer what arrives;
3. on ``SEAT_ADDED``, bind the capabilities this sender wants;
4. on ``DEVICE_ADDED``, keep the device that carries each capability —
   **devices only ever come from an event**, never from the context;
5. on ``DEVICE_RESUMED``, call ``ei_device_start_emulating``;
6. per emission, send the event *and* ``ei_device_frame``, or nothing is
   delivered.

The previous binding did none of that. It held only the ``struct ei *``
context and passed it to entry points that take a ``struct ei_device *`` —
pointer type confusion in a C library — and without ``frame()`` no event
would have arrived even had the pointers been right.

**Fail-closed by construction.** Every failure below raises
:class:`LibeiUnavailable`, which ``keyboard`` / ``mouse`` already treat as
"use the ydotool CLI". The handshake is bounded by a deadline and the result
is cached per process (:func:`connected_backend`), so a host where libei is
installed but unusable pays the probe once, not once per keystroke.

The enum values are libei's, from ``libei.h``. They are the one part of this
module that a wrong guess would silently change — see ``Progress.md``. A
mismatch degrades safely rather than misfiring: capabilities that do not
match mean no device ever reports them, the handshake times out, and the CLI
takes over.
"""
from __future__ import annotations

import ctypes
import os
import select
import threading
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from je_auto_control.linux_wayland import oeffis
from je_auto_control.linux_wayland._ctypes_bind import BoundSymbols, bind
from je_auto_control.linux_wayland._layout import layout_origin
from je_auto_control.utils.exception.exceptions import AutoControlException


_LIBRARY_CANDIDATES = ("ei", "libei", "libei.so.1", "libei.so.0")

# enum ei_device_capability — a **bitmask**, not a sequence. Verified against
# libei.h (Debian 1.5.0-3 and upstream main, which agree on these six).
EI_DEVICE_CAP_POINTER = 1 << 0
EI_DEVICE_CAP_POINTER_ABSOLUTE = 1 << 1
EI_DEVICE_CAP_KEYBOARD = 1 << 2
EI_DEVICE_CAP_TOUCH = 1 << 3
EI_DEVICE_CAP_SCROLL = 1 << 4
EI_DEVICE_CAP_BUTTON = 1 << 5

# enum ei_event_type — only the ones this sender has to answer. The block
# starts at 1 and increments implicitly through DEVICE_RESUMED before jumping
# to 90; the values below are that first run, verified against libei.h.
EI_EVENT_CONNECT = 1
EI_EVENT_DISCONNECT = 2
EI_EVENT_SEAT_ADDED = 3
EI_EVENT_SEAT_REMOVED = 4
EI_EVENT_DEVICE_ADDED = 5
EI_EVENT_DEVICE_REMOVED = 6
EI_EVENT_DEVICE_PAUSED = 7
EI_EVENT_DEVICE_RESUMED = 8

#: Capabilities bound on every seat. Buttons and scroll ride along with the
#: pointer device wherever the compositor grants them.
_WANTED_CAPS = (EI_DEVICE_CAP_KEYBOARD, EI_DEVICE_CAP_POINTER_ABSOLUTE,
                EI_DEVICE_CAP_BUTTON, EI_DEVICE_CAP_SCROLL)

#: Without these two, half the public API would silently do nothing, so a
#: partial grant is treated as no grant at all.
_REQUIRED_CAPS = (EI_DEVICE_CAP_KEYBOARD, EI_DEVICE_CAP_POINTER_ABSOLUTE)

#: Handshake budget once the EIS fd is in hand. The portal's own consent
#: wait already happened in :mod:`oeffis`; this is just protocol round trips.
HANDSHAKE_TIMEOUT = 3.0

#: One region of an absolute pointer's coordinate space: ``(x, y, w, h)``.
Region = Tuple[int, int, int, int]

#: Ceiling on ``ei_device_get_region`` enumeration. libei ends the list with
#: NULL and a desktop has a handful of outputs; this only stops a library
#: whose contract differs from hanging the caller's mouse move forever.
_MAX_REGIONS = 64

#: One wheel click, in the units ``ei_device_scroll_discrete`` takes. From
#: libei.h: "A discrete scroll event is based logical scroll units (equivalent
#: to one mouse wheel click). The value for one scroll unit is 120."
SCROLL_UNIT = 120

_VOID = ctypes.c_void_p
_PROTOTYPES = (
    ("ei_new_sender", _VOID, (_VOID,)),
    ("ei_unref", _VOID, (_VOID,)),
    ("ei_setup_backend_fd", ctypes.c_int, (_VOID, ctypes.c_int)),
    ("ei_setup_backend_socket", ctypes.c_int, (_VOID, ctypes.c_char_p)),
    ("ei_get_fd", ctypes.c_int, (_VOID,)),
    ("ei_dispatch", None, (_VOID,)),
    ("ei_get_event", _VOID, (_VOID,)),
    ("ei_event_unref", _VOID, (_VOID,)),
    ("ei_event_get_type", ctypes.c_int, (_VOID,)),
    ("ei_event_get_seat", _VOID, (_VOID,)),
    ("ei_event_get_device", _VOID, (_VOID,)),
    ("ei_device_ref", _VOID, (_VOID,)),
    ("ei_device_unref", _VOID, (_VOID,)),
    ("ei_device_has_capability", ctypes.c_bool, (_VOID, ctypes.c_int)),
    ("ei_device_start_emulating", None, (_VOID, ctypes.c_uint32)),
    ("ei_device_stop_emulating", None, (_VOID,)),
    ("ei_device_frame", None, (_VOID, ctypes.c_uint64)),
    ("ei_device_keyboard_key", None, (_VOID, ctypes.c_uint32, ctypes.c_bool)),
    ("ei_device_pointer_motion_absolute", None,
     (_VOID, ctypes.c_double, ctypes.c_double)),
    ("ei_device_get_region", _VOID, (_VOID, ctypes.c_size_t)),
    ("ei_region_get_x", ctypes.c_uint32, (_VOID,)),
    ("ei_region_get_y", ctypes.c_uint32, (_VOID,)),
    ("ei_region_get_width", ctypes.c_uint32, (_VOID,)),
    ("ei_region_get_height", ctypes.c_uint32, (_VOID,)),
    ("ei_device_button_button", None, (_VOID, ctypes.c_uint32, ctypes.c_bool)),
    ("ei_device_scroll_discrete", None,
     (_VOID, ctypes.c_int32, ctypes.c_int32)),
    ("ei_now", ctypes.c_uint64, (_VOID,)),
)


class LibeiUnavailable(AutoControlException, RuntimeError):
    """libei is missing, or a sender cannot be brought up on this session.

    Inherits both bases on purpose. ``AutoControlException`` is what every
    containment boundary in the framework catches, and a sibling of it
    escapes all of them — see that class's docstring. ``RuntimeError`` is
    kept because the backend probes here and in ``_select_input`` were
    written to catch it, and because "libei will not come up" is a runtime
    environment fact rather than a caller mistake.
    """


def _load_symbols() -> Optional[BoundSymbols]:
    """Resolve every libei entry point, or None if one is missing.

    ``ei_seat_bind_capabilities`` is bound unchecked because it is variadic:
    ctypes has to infer each argument's type at the call site.
    """
    return bind(_LIBRARY_CANDIDATES, _PROTOTYPES,
                unchecked=("ei_seat_bind_capabilities",))


def _default_socket_path() -> bytes:
    """Where a compositor that exposes EIS on disk would put the socket."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        return b"/run/user/1000/eis-0"
    return f"{runtime}/eis-0".encode("utf-8")


def _in_any_region(regions: Sequence[Region], x: int, y: int) -> bool:
    """Whether ``(x, y)`` falls inside one of ``regions``.

    The right and bottom edges are outside, which is measured rather than
    assumed: against a real EIS peer offering one ``(0, 0, 1920, 1080)``
    region, ``(1919, 1079)`` arrives and ``(1920, 1080)`` does not.
    """
    return any(left <= x < left + width and top <= y < top + height
               for left, top, width, height in regions)


class LibeiBackend:
    """A libei sender that has completed the handshake and can emit input.

    ``LibeiBackend()`` only probes for the library; :meth:`connect` performs
    the portal request and the protocol handshake. Tests inject a fake
    ``symbols=`` object exposing the same entry-point names.
    """

    def __init__(self, *, symbols: Optional[BoundSymbols] = None,
                 portal_connect: Optional[Callable[..., tuple]] = None) -> None:
        self._symbols = symbols if symbols is not None else _load_symbols()
        self._portal_connect = portal_connect or oeffis.connect_eis_fd
        self._ei: Optional[int] = None
        self._backend_open = False
        self._handshake_complete = False
        self._session = None
        self._devices: Dict[int, int] = {}
        self._emulating: Dict[int, bool] = {}
        self._sequence = 0
        self._lock = threading.RLock()

    @property
    def is_available(self) -> bool:
        """Whether libei itself resolved. Says nothing about the session."""
        return self._symbols is not None

    @property
    def is_connected(self) -> bool:
        """Whether the handshake finished and a device is emulating."""
        return self._ei is not None and self._has_required_devices()

    def connect(self, *, timeout: float = HANDSHAKE_TIMEOUT,
                socket_path: Optional[bytes] = None) -> None:
        """Open a backend and run the handshake through to a live device.

        :param timeout: seconds for the protocol handshake, once connected.
        :param socket_path: bypass the portal and use this EIS socket.
        """
        if not self.is_available:
            raise LibeiUnavailable("libei.so.* not found on the loader path")
        with self._lock:
            if self.is_connected:
                return
            sender = self._symbols.ei_new_sender(None)
            if not sender:
                raise LibeiUnavailable("ei_new_sender returned NULL")
            self._ei = sender
            try:
                self._open_backend(socket_path)
                self._handshake(time.monotonic() + max(0.0, timeout))
                # Reaching a live device is what makes ei_unref safe on this
                # libei, so _teardown reads this rather than guessing.
                self._handshake_complete = True
            except BaseException:
                self._teardown()
                raise

    def disconnect(self) -> None:
        """Release the devices, the sender, and the portal session."""
        with self._lock:
            self._teardown()

    # --- emission ---------------------------------------------------------

    def press_key(self, keycode: int) -> None:
        """Send a keydown for one evdev key code."""
        self._emit(EI_DEVICE_CAP_KEYBOARD, lambda device:
                   self._symbols.ei_device_keyboard_key(
                       device, int(keycode), True))

    def release_key(self, keycode: int) -> None:
        """Send a keyup for one evdev key code."""
        self._emit(EI_DEVICE_CAP_KEYBOARD, lambda device:
                   self._symbols.ei_device_keyboard_key(
                       device, int(keycode), False))

    def set_position(self, x: int, y: int) -> None:
        """Move the pointer to an absolute screen position.

        The coordinate is mapped into the device's own space first — see
        :meth:`_region_point`, which is also where a point no region covers
        is turned into a refusal instead of a silent no-op.
        """
        self._emit(EI_DEVICE_CAP_POINTER_ABSOLUTE, lambda device:
                   self._symbols.ei_device_pointer_motion_absolute(
                       device, *self._region_point(device, x, y)))

    def press_button(self, button_code: int) -> None:
        """Press one BTN_* code (272 is BTN_LEFT)."""
        self._emit(EI_DEVICE_CAP_BUTTON, lambda device:
                   self._symbols.ei_device_button_button(
                       device, int(button_code), True))

    def release_button(self, button_code: int) -> None:
        """Release one BTN_* code."""
        self._emit(EI_DEVICE_CAP_BUTTON, lambda device:
                   self._symbols.ei_device_button_button(
                       device, int(button_code), False))

    def click_button(self, button_code: int) -> None:
        """Press then release one BTN_* code."""
        self.press_button(button_code)
        self.release_button(button_code)

    def scroll(self, dx: int, dy: int) -> None:
        """Scroll by whole wheel clicks on either axis.

        libei measures discrete scroll in 120ths of a click — the same
        convention as Windows' ``WHEEL_DELTA`` — so a raw detent count is a
        120th of the scroll the caller asked for. Measured against a real EIS
        peer, which is also where libei's own "suspicious discrete event value
        1, did you mean 120?" bug warning showed up.
        """
        self._emit(EI_DEVICE_CAP_SCROLL, lambda device:
                   self._symbols.ei_device_scroll_discrete(
                       device, int(dx) * SCROLL_UNIT, int(dy) * SCROLL_UNIT))

    # --- handshake --------------------------------------------------------

    def _open_backend(self, socket_path: Optional[bytes]) -> None:
        """Attach the sender to an EIS fd from the portal, or to a socket.

        The portal is the route that works on GNOME and KDE. Where
        liboeffis is not installed there is still the well-known socket
        some compositors publish, so that is tried rather than giving up.
        """
        if socket_path is None and not oeffis.is_available():
            socket_path = _default_socket_path()
        if socket_path is not None:
            code = self._symbols.ei_setup_backend_socket(self._ei, socket_path)
            if code != 0:
                raise LibeiUnavailable(
                    f"ei_setup_backend_socket returned {code}",
                )
            self._backend_open = True
            return
        try:
            eis_fd, session = self._portal_connect()
        except oeffis.OeffisUnavailable as error:
            raise LibeiUnavailable(str(error)) from error
        self._session = session
        code = self._symbols.ei_setup_backend_fd(self._ei, int(eis_fd))
        if code != 0:
            raise LibeiUnavailable(f"ei_setup_backend_fd returned {code}")
        self._backend_open = True

    def _handshake(self, deadline: float) -> None:
        """Pump events until the devices we need are emulating."""
        while not self._has_required_devices():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LibeiUnavailable(
                    "libei connected but no seat offered both a keyboard and "
                    "an absolute pointer within the handshake timeout",
                )
            self._pump(min(remaining, 0.25))

    def _pump(self, timeout: float) -> None:
        """Dispatch libei and answer every event that is waiting."""
        poll_fd = int(self._symbols.ei_get_fd(self._ei))
        if poll_fd < 0:
            raise LibeiUnavailable("ei_get_fd returned no pollable fd")
        if timeout > 0:
            ready, _, _ = select.select([poll_fd], [], [], timeout)
            if not ready:
                return
        self._symbols.ei_dispatch(self._ei)
        while True:
            event = self._symbols.ei_get_event(self._ei)
            if not event:
                return
            try:
                self._on_event(event)
            finally:
                self._symbols.ei_event_unref(event)

    def _on_event(self, event: int) -> None:
        """Answer one libei event."""
        event_type = int(self._symbols.ei_event_get_type(event))
        if event_type == EI_EVENT_SEAT_ADDED:
            self._bind_seat(self._symbols.ei_event_get_seat(event))
        elif event_type == EI_EVENT_DEVICE_ADDED:
            self._remember_device(self._symbols.ei_event_get_device(event))
        elif event_type == EI_EVENT_DEVICE_RESUMED:
            self._start_emulating(self._symbols.ei_event_get_device(event))
        elif event_type in (EI_EVENT_DEVICE_PAUSED, EI_EVENT_DEVICE_REMOVED):
            self._forget_device(self._symbols.ei_event_get_device(event))
        elif event_type == EI_EVENT_DISCONNECT:
            raise LibeiUnavailable("the compositor disconnected the sender")

    def _bind_seat(self, seat: int) -> None:
        """Ask a seat for the capabilities this sender emits.

        ``ei_seat_bind_capabilities`` is variadic and NULL-terminated, so the
        arguments are passed as explicit ctypes values — an ``argtypes``
        tuple cannot describe a variadic call.
        """
        if not seat:
            return
        args = [ctypes.c_void_p(seat)]
        args.extend(ctypes.c_int(cap) for cap in _WANTED_CAPS)
        args.append(ctypes.c_void_p(None))
        self._symbols.ei_seat_bind_capabilities(*args)

    def _remember_device(self, device: int) -> None:
        """Keep a reference to a device for each capability it carries."""
        if not device:
            return
        kept = False
        for cap in _WANTED_CAPS:
            if not self._symbols.ei_device_has_capability(device, cap):
                continue
            if not kept:
                self._symbols.ei_device_ref(device)
                kept = True
            self._devices[cap] = device

    def _start_emulating(self, device: int) -> None:
        """Mark a resumed device ready and open its emulation sequence."""
        if not device or device not in self._devices.values():
            return
        self._sequence += 1
        self._symbols.ei_device_start_emulating(device, self._sequence)
        self._emulating[device] = True

    def _forget_device(self, device: int) -> None:
        """Drop a paused or removed device; emissions then fail closed."""
        if not device:
            return
        self._emulating.pop(device, None)
        stale = [cap for cap, known in self._devices.items() if known == device]
        for cap in stale:
            del self._devices[cap]
        self._symbols.ei_device_unref(device)

    def _has_required_devices(self) -> bool:
        return all(self._emulating.get(self._devices.get(cap, 0), False)
                   for cap in _REQUIRED_CAPS)

    # --- coordinate space -------------------------------------------------

    def _device_regions(self, device: int) -> List[Region]:
        """The regions this device accepts absolute motion in.

        libei reports them in its own space, offsets included: a device whose
        region sits at ``x=1280`` takes ``1380`` for a point 100 pixels into
        it, not ``100``. An empty list means the device declared none, and a
        device with no regions accepts any coordinate — both measured against
        a real EIS peer in ``docker/eis_verify.py``.
        """
        regions: List[Region] = []
        for index in range(_MAX_REGIONS):
            region = self._symbols.ei_device_get_region(device, index)
            if not region:
                break
            regions.append((
                int(self._symbols.ei_region_get_x(region)),
                int(self._symbols.ei_region_get_y(region)),
                int(self._symbols.ei_region_get_width(region)),
                int(self._symbols.ei_region_get_height(region)),
            ))
        return regions

    def _region_point(self, device: int, x: int, y: int) -> Tuple[float, float]:
        """Map a layout coordinate into the space ``device`` accepts.

        **libei discards an absolute motion that lands in no region, and says
        nothing about it** — no return code, no event, no log the caller can
        see. ``set_position`` would return as though the pointer had moved.
        That is the failure this method exists to prevent, and it is measured,
        not inferred: against a real EIS peer, a point outside every region
        produced no server-side event at all.

        The two spaces can genuinely differ. Region offsets are ``uint32``, so
        no compositor *can* advertise a region left of or above the origin,
        while this project's layout space starts at
        :func:`je_auto_control.linux_wayland._layout.layout_origin` and
        goes negative the moment a monitor sits left of the primary one — the
        exact layout ``docker/wayland_verify.py`` exercises on the capture
        side. Where the raw point misses, the origin-normalised one is tried,
        which is the translation that keeps input and capture addressing the
        same pixel. If that misses too, the caller gets a refusal and
        ``_select_input.emitted`` hands the move to the ydotool path.
        """
        regions = self._device_regions(device)
        if not regions or _in_any_region(regions, x, y):
            return (float(x), float(y))
        origin_x, origin_y = layout_origin()
        moved_x, moved_y = x - origin_x, y - origin_y
        if (origin_x or origin_y) and _in_any_region(regions, moved_x, moved_y):
            return (float(moved_x), float(moved_y))
        raise LibeiUnavailable(
            f"({x}, {y}) lies outside every region this pointer accepts "
            f"{regions}; libei drops such a motion without reporting it, so "
            "the move is refused here for the CLI path to take",
        )

    # --- plumbing ---------------------------------------------------------

    def _emit(self, capability: int, send: Callable[[int], None]) -> None:
        """Send one event on the device carrying ``capability``, then frame.

        Without the trailing ``ei_device_frame`` libei buffers the event and
        the compositor never sees it, so the two belong in one place.
        """
        with self._lock:
            if self._ei is None:
                raise LibeiUnavailable("libei sender is not connected")
            # Pause / resume arrive asynchronously; read them before deciding
            # the device is still usable.
            self._pump(0.0)
            device = self._devices.get(capability)
            if not device or not self._emulating.get(device, False):
                raise LibeiUnavailable(
                    f"no libei device is emulating capability {capability}",
                )
            send(device)
            self._symbols.ei_device_frame(device, self._symbols.ei_now(self._ei))

    def _teardown(self) -> None:
        """Release what is safe to release; abandon what is not.

        ``ei_unref`` **segfaults** on libei 1.3.901 on a context whose backend
        was opened but whose handshake never progressed. Measured, not
        inferred — ``docker/libei_verify.py`` walks the states one call at a
        time against the real library, and ``docker/eis_verify.py`` adds the
        live one by running a real EIS peer:

        =========================================  ==========
        state                                      ``ei_unref``
        =========================================  ==========
        context created, no backend set up         safe
        ``ei_setup_backend_socket`` failed (-2)     safe
        backend open, handshake never progressed   **SIGSEGV**
        handshake completed, devices emulating     safe
        =========================================  ==========

        ``ei_disconnect`` crashes in the same state, so it is not a
        refcounting mistake on our side — it is tearing down a connection
        whose EI handshake never progressed. The header documents ``unref``
        as the correct release for every outcome, so this reads as an
        upstream bug rather than misuse.

        So the release is chosen by state. A session that reached a live
        device is unreffed normally, which is the common path and no longer
        leaks. Only the crashing state is abandoned — its context and fd are
        dropped without unref, a few hundred bytes and one descriptor per
        process, since :func:`connected_backend` probes only once. A segfault
        in a library that drives someone's desktop is far worse than that.
        """
        if self._ei is not None and self._safe_to_unref():
            for device in set(self._devices.values()):
                _quietly(lambda handle=device:
                         self._symbols.ei_device_unref(handle))
            _quietly(lambda: self._symbols.ei_unref(self._ei))
        self._devices.clear()
        self._emulating.clear()
        self._ei = None
        self._backend_open = False
        self._handshake_complete = False
        if self._session is not None:
            # liboeffis is a different library and closing the portal session
            # is what actually revokes the grant, so this always runs.
            _quietly(self._session.close)
            self._session = None

    def _safe_to_unref(self) -> bool:
        """Whether this context is in a state libei survives being unreffed in.

        The two safe states are "no backend was ever opened" and "the
        handshake completed". Everything in between is the measured crash.
        """
        return not self._backend_open or self._handshake_complete


def _quietly(action: Callable[[], object]) -> None:
    """Run a cleanup step; a failing one must not mask the real error."""
    try:
        action()
    except (AttributeError, OSError, ValueError, RuntimeError):
        pass


_DEFAULT_BACKEND: Optional[LibeiBackend] = None
_PROBE_FAILED = False
_DEFAULT_LOCK = threading.Lock()


def connected_backend() -> Optional[LibeiBackend]:
    """Return a connected backend, or None — probing at most once.

    The probe involves a portal round trip and a consent dialog, so a host
    where libei cannot be used must pay for that discovery once rather than
    on every keystroke. Callers treat None as "use the ydotool CLI".
    """
    global _DEFAULT_BACKEND, _PROBE_FAILED
    with _DEFAULT_LOCK:
        if _DEFAULT_BACKEND is not None:
            return _DEFAULT_BACKEND
        if _PROBE_FAILED:
            return None
        backend = LibeiBackend()
        if not backend.is_available:
            _PROBE_FAILED = True
            return None
        try:
            backend.connect()
        except (LibeiUnavailable, OSError, ValueError, AttributeError):
            _PROBE_FAILED = True
            return None
        _DEFAULT_BACKEND = backend
        return _DEFAULT_BACKEND


def get_default_backend() -> Optional[LibeiBackend]:
    """Return the cached backend if libei resolved, without connecting."""
    with _DEFAULT_LOCK:
        if _DEFAULT_BACKEND is not None:
            return _DEFAULT_BACKEND
    backend = LibeiBackend()
    return backend if backend.is_available else None


def reset_default_backend() -> None:
    """Test hook — drop the cached backend so the probe runs fresh."""
    global _DEFAULT_BACKEND, _PROBE_FAILED
    with _DEFAULT_LOCK:
        if _DEFAULT_BACKEND is not None:
            _quietly(_DEFAULT_BACKEND.disconnect)
        _DEFAULT_BACKEND = None
        _PROBE_FAILED = False


__all__ = [
    "EI_DEVICE_CAP_BUTTON", "EI_DEVICE_CAP_KEYBOARD",
    "EI_DEVICE_CAP_POINTER_ABSOLUTE", "EI_DEVICE_CAP_SCROLL",
    "HANDSHAKE_TIMEOUT", "LibeiBackend", "LibeiUnavailable",
    "connected_backend", "get_default_backend", "reset_default_backend",
]
