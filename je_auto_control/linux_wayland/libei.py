"""ctypes binding for libei — Wayland's HID-layer input emulation library.

libei runs at the kernel-input-event layer, which is *much* faster
than spawning ``wtype`` / ``ydotool`` per keystroke (a few µs vs. a
few ms). Compositors that expose the
``zwp_input_method_unstable_v2`` portal or the libei sender protocol
let an unprivileged client emit pointer / key events without the
sandbox veto.

The binding is opt-in: callers go through :class:`LibeiBackend`, and
:func:`LibeiBackend.is_available` probes for ``libei.so.1`` on the
loader path. When the library is missing, callers should fall through
to the CLI shims in :mod:`keyboard` / :mod:`mouse` — that's what the
backend selector in :func:`select_input_backend` does.

This module deliberately stays pure-Python so the test suite can run
on hosts without libei: the ctypes bindings are introduced lazily
through :class:`_LibeiSymbols`, and every external call is wrapped in
a method that's easy to mock.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import threading
from dataclasses import dataclass
from typing import Optional


_LIBRARY_CANDIDATES = ("ei", "libei", "libei.so.1", "libei.so.0")


class LibeiUnavailable(RuntimeError):
    """Raised when libei isn't installed or the sender can't connect."""


@dataclass(frozen=True)
class _LibeiSymbols:
    """Function pointers we resolve out of ``libei.so.*``."""

    lib: ctypes.CDLL
    ei_new_sender: ctypes.CFUNCTYPE
    ei_setup_backend_socket: ctypes.CFUNCTYPE
    ei_device_keyboard_key: ctypes.CFUNCTYPE
    ei_device_pointer_motion_absolute: ctypes.CFUNCTYPE
    ei_device_button_button: ctypes.CFUNCTYPE
    ei_device_scroll: ctypes.CFUNCTYPE
    ei_unref: ctypes.CFUNCTYPE


def _try_load_library() -> Optional[ctypes.CDLL]:
    """Probe ``libei.so.*`` on the loader path; return None if absent."""
    for name in _LIBRARY_CANDIDATES:
        resolved = ctypes.util.find_library(name)
        if resolved is None:
            continue
        try:
            return ctypes.CDLL(resolved, use_errno=True)
        except (OSError, RuntimeError):
            continue
    return None


def _bind_symbols(lib: ctypes.CDLL) -> Optional[_LibeiSymbols]:
    """Pull every libei function we use out of the shared object."""
    try:
        new_sender = lib.ei_new_sender
        setup_socket = lib.ei_setup_backend_socket
        device_key = lib.ei_device_keyboard_key
        device_motion = lib.ei_device_pointer_motion_absolute
        device_button = lib.ei_device_button_button
        device_scroll = lib.ei_device_scroll
        unref = lib.ei_unref
    except AttributeError:
        return None
    # Argument / return types match the upstream API. libei uses opaque
    # handles + ints + uint32 booleans, so the binding stays compact.
    new_sender.restype = ctypes.c_void_p
    new_sender.argtypes = (ctypes.c_char_p,)
    setup_socket.restype = ctypes.c_int
    setup_socket.argtypes = (ctypes.c_void_p, ctypes.c_char_p)
    device_key.restype = ctypes.c_int
    device_key.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32)
    device_motion.restype = ctypes.c_int
    device_motion.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double)
    device_button.restype = ctypes.c_int
    device_button.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32)
    device_scroll.restype = ctypes.c_int
    device_scroll.argtypes = (ctypes.c_void_p, ctypes.c_double, ctypes.c_double)
    unref.restype = None
    unref.argtypes = (ctypes.c_void_p,)
    return _LibeiSymbols(
        lib=lib, ei_new_sender=new_sender,
        ei_setup_backend_socket=setup_socket,
        ei_device_keyboard_key=device_key,
        ei_device_pointer_motion_absolute=device_motion,
        ei_device_button_button=device_button,
        ei_device_scroll=device_scroll, ei_unref=unref,
    )


class LibeiBackend:
    """Native libei sender — thread-safe, lazy initialisation.

    ``LibeiBackend()`` cheaply probes for libei but does NOT connect;
    call :meth:`connect` to open the socket. Tests inject a fake
    :class:`_LibeiSymbols` via the ``symbols=`` keyword so the
    behaviour can be exercised without ctypes.
    """

    def __init__(self, *, sender_name: bytes = b"je_auto_control",
                 symbols: Optional[_LibeiSymbols] = None) -> None:
        self._sender_name = sender_name
        self._symbols = symbols if symbols is not None else _load_symbols()
        self._handle: Optional[int] = None
        self._lock = threading.Lock()

    @property
    def is_available(self) -> bool:
        return self._symbols is not None

    def connect(self, *, socket_path: Optional[bytes] = None) -> None:
        """Open the libei sender socket (default: $XDG_RUNTIME_DIR/eis-0)."""
        if not self.is_available:
            raise LibeiUnavailable(
                "libei.so.* not found on the loader path",
            )
        with self._lock:
            if self._handle is not None:
                return
            sender = self._symbols.ei_new_sender(self._sender_name)
            if not sender:
                raise LibeiUnavailable("ei_new_sender returned NULL")
            chosen_socket = socket_path or _default_socket_path()
            rc = self._symbols.ei_setup_backend_socket(sender, chosen_socket)
            if rc != 0:
                self._symbols.ei_unref(sender)
                raise LibeiUnavailable(
                    f"ei_setup_backend_socket returned {rc}",
                )
            self._handle = sender

    def disconnect(self) -> None:
        with self._lock:
            if self._handle is None:
                return
            if self._symbols is not None:
                self._symbols.ei_unref(self._handle)
            self._handle = None

    def press_key(self, keycode: int) -> None:
        """Send a keydown for one evdev key code via libei."""
        self._require_connected()
        self._symbols.ei_device_keyboard_key(self._handle, int(keycode), 1)

    def release_key(self, keycode: int) -> None:
        self._require_connected()
        self._symbols.ei_device_keyboard_key(self._handle, int(keycode), 0)

    def set_position(self, x: int, y: int) -> None:
        self._require_connected()
        self._symbols.ei_device_pointer_motion_absolute(
            self._handle, float(x), float(y),
        )

    def click_button(self, button_code: int) -> None:
        """Press + release one BTN_* code (e.g. 272 for left click)."""
        self._require_connected()
        self._symbols.ei_device_button_button(self._handle, int(button_code), 1)
        self._symbols.ei_device_button_button(self._handle, int(button_code), 0)

    def press_button(self, button_code: int) -> None:
        self._require_connected()
        self._symbols.ei_device_button_button(self._handle, int(button_code), 1)

    def release_button(self, button_code: int) -> None:
        self._require_connected()
        self._symbols.ei_device_button_button(self._handle, int(button_code), 0)

    def scroll(self, dx: int, dy: int) -> None:
        self._require_connected()
        self._symbols.ei_device_scroll(self._handle, float(dx), float(dy))

    def _require_connected(self) -> None:
        if not self.is_available:
            raise LibeiUnavailable("libei not loaded")
        if self._handle is None:
            raise LibeiUnavailable(
                "libei sender not connected; call connect() first",
            )


def _load_symbols() -> Optional[_LibeiSymbols]:
    lib = _try_load_library()
    if lib is None:
        return None
    return _bind_symbols(lib)


def _default_socket_path() -> bytes:
    import os
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        return b"/run/user/1000/eis-0"
    return f"{runtime}/eis-0".encode("utf-8")


# Cached default sender — created on first use, kept for the process
# lifetime so input latency isn't dominated by sender setup.
_DEFAULT_BACKEND: Optional[LibeiBackend] = None
_DEFAULT_LOCK = threading.Lock()


def get_default_backend() -> Optional[LibeiBackend]:
    """Return the cached :class:`LibeiBackend`, or None when libei is absent."""
    global _DEFAULT_BACKEND
    with _DEFAULT_LOCK:
        if _DEFAULT_BACKEND is not None:
            return _DEFAULT_BACKEND
        backend = LibeiBackend()
        if not backend.is_available:
            return None
        _DEFAULT_BACKEND = backend
    return _DEFAULT_BACKEND


def reset_default_backend() -> None:
    """Test hook — drop the cached default so probe runs fresh."""
    global _DEFAULT_BACKEND
    with _DEFAULT_LOCK:
        if _DEFAULT_BACKEND is not None:
            try:
                _DEFAULT_BACKEND.disconnect()
            except LibeiUnavailable:
                pass
        _DEFAULT_BACKEND = None


__all__ = [
    "LibeiBackend", "LibeiUnavailable",
    "get_default_backend", "reset_default_backend",
]
