"""ctypes binding for liboeffis — the portal half of the libei handshake.

libei needs an EIS socket, and on GNOME / KDE that socket is not a path on
disk: it is a file descriptor handed over D-Bus by
``org.freedesktop.portal.RemoteDesktop.ConnectToEIS``, at the end of a
three-call asynchronous session dance (``CreateSession`` → ``SelectDevices``
→ ``Start``). A file descriptor cannot be received through the ``gdbus``
command line, so the CLI trick that works for the Screenshot portal (see
:mod:`portal`) cannot work here — it would need a D-Bus client that speaks
SCM_RIGHTS.

``liboeffis`` ships with libei precisely so clients do not have to write
that. It performs the whole portal dance and hands back the EIS fd, which is
what :mod:`libei` then passes to ``ei_setup_backend_fd``.

Everything here is fail-closed: if the library is missing, the portal denies
the request, or the user dismisses the consent dialog, the caller gets None
or an exception and falls back to the ydotool CLI.
"""
from __future__ import annotations

import ctypes
import select
import time
from typing import Optional, Tuple

from je_auto_control.linux_wayland._ctypes_bind import BoundSymbols, bind


_LIBRARY_CANDIDATES = ("oeffis", "liboeffis", "liboeffis.so.1", "liboeffis.so.0")

# enum oeffis_device — a bitmask of what the session may do. Verified against
# liboeffis.h (Debian 1.5.0-3 and upstream main agree).
OEFFIS_DEVICE_ALL_DEVICES = 0     # the header's "everything" sentinel
OEFFIS_DEVICE_KEYBOARD = 1 << 0
OEFFIS_DEVICE_POINTER = 1 << 1
OEFFIS_DEVICE_TOUCHSCREEN = 1 << 2

#: What this backend actually emits. Asking for the touchscreen we never use
#: would widen the grant the user is consenting to for no benefit, and an
#: explicit mask cannot be misread as the ``= 0`` sentinel either way.
OEFFIS_DEVICE_DEFAULT = OEFFIS_DEVICE_KEYBOARD | OEFFIS_DEVICE_POINTER

# enum oeffis_event_type — note CLOSED precedes DISCONNECTED, which is the
# opposite of the order the names suggest.
OEFFIS_EVENT_NONE = 0
OEFFIS_EVENT_CONNECTED_TO_EIS = 1
OEFFIS_EVENT_CLOSED = 2
OEFFIS_EVENT_DISCONNECTED = 3

#: The consent dialog is a human in the loop, so this is a human-scale wait.
DEFAULT_TIMEOUT = 30.0

_PROTOTYPES = (
    ("oeffis_new", ctypes.c_void_p, (ctypes.c_void_p,)),
    ("oeffis_unref", ctypes.c_void_p, (ctypes.c_void_p,)),
    ("oeffis_create_session", None, (ctypes.c_void_p, ctypes.c_uint32)),
    ("oeffis_get_fd", ctypes.c_int, (ctypes.c_void_p,)),
    ("oeffis_dispatch", None, (ctypes.c_void_p,)),
    ("oeffis_get_event", ctypes.c_int, (ctypes.c_void_p,)),
    ("oeffis_get_eis_fd", ctypes.c_int, (ctypes.c_void_p,)),
    ("oeffis_get_error_message", ctypes.c_char_p, (ctypes.c_void_p,)),
)


class OeffisUnavailable(RuntimeError):
    """liboeffis is missing, or the portal refused to hand over an EIS fd."""


def load_symbols() -> Optional[BoundSymbols]:
    """Resolve liboeffis, or None when it is not installed."""
    return bind(_LIBRARY_CANDIDATES, _PROTOTYPES)


def is_available() -> bool:
    """Whether the portal route to an EIS fd can be attempted at all."""
    return load_symbols() is not None


def _describe(symbols: BoundSymbols, handle: int) -> str:
    """The library's own error text, when it has one."""
    try:
        message = symbols.oeffis_get_error_message(handle)
    except (AttributeError, OSError, ValueError):
        return ""
    if not message:
        return ""
    if isinstance(message, bytes):
        return message.decode("utf-8", errors="replace")
    return str(message)


def _pump(symbols: BoundSymbols, handle: int, deadline: float) -> int:
    """Wait for one oeffis event, or 0 when the deadline passes."""
    poll_fd = symbols.oeffis_get_fd(handle)
    if poll_fd < 0:
        raise OeffisUnavailable("oeffis_get_fd returned no pollable fd")
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return OEFFIS_EVENT_NONE
        ready, _, _ = select.select([poll_fd], [], [], remaining)
        if not ready:
            return OEFFIS_EVENT_NONE
        symbols.oeffis_dispatch(handle)
        event = int(symbols.oeffis_get_event(handle))
        if event != OEFFIS_EVENT_NONE:
            return event


def connect_eis_fd(devices: int = OEFFIS_DEVICE_DEFAULT,
                   timeout: float = DEFAULT_TIMEOUT,
                   symbols: Optional[BoundSymbols] = None) -> Tuple[int, object]:
    """Run the portal session and return ``(eis_fd, session_handle)``.

    The session handle must be kept alive for as long as the EIS fd is used:
    dropping it tears the portal session down and the compositor stops
    accepting input from it.

    :param devices: bitmask of ``OEFFIS_DEVICE_*`` to request.
    :param timeout: seconds to wait, including any consent dialog.
    :param symbols: injected entry points, for tests.
    :return: the EIS file descriptor and the handle owning the session.
    """
    resolved = symbols if symbols is not None else load_symbols()
    if resolved is None:
        raise OeffisUnavailable("liboeffis.so.* not found on the loader path")
    handle = resolved.oeffis_new(None)
    if not handle:
        raise OeffisUnavailable("oeffis_new returned NULL")
    try:
        resolved.oeffis_create_session(handle, int(devices))
        event = _pump(resolved, handle, time.monotonic() + max(0.0, timeout))
        _require_connected(resolved, handle, event, timeout)
        eis_fd = int(resolved.oeffis_get_eis_fd(handle))
        if eis_fd < 0:
            raise OeffisUnavailable(
                "the portal reported success but handed over no EIS fd",
            )
    except BaseException:
        _release(resolved, handle)
        raise
    return eis_fd, _Session(resolved, handle)


def _require_connected(symbols: BoundSymbols, handle: int, event: int,
                       timeout: float) -> None:
    """Turn anything but a successful connection into a clear failure."""
    if event == OEFFIS_EVENT_CONNECTED_TO_EIS:
        return
    if event == OEFFIS_EVENT_NONE:
        raise OeffisUnavailable(
            f"the desktop portal did not answer within {timeout:g}s "
            f"(a consent dialog may be waiting)",
        )
    detail = _describe(symbols, handle)
    reason = ("the desktop portal closed the remote-desktop session"
              if event == OEFFIS_EVENT_CLOSED
              else "the desktop portal disconnected the remote-desktop session")
    raise OeffisUnavailable(f"{reason}{': ' + detail if detail else ''}")


def _release(symbols: BoundSymbols, handle: int) -> None:
    """Drop the oeffis context; never raise from cleanup."""
    try:
        symbols.oeffis_unref(handle)
    except (AttributeError, OSError, ValueError):
        pass


class _Session:
    """Keeps the portal session alive; releasing it ends the grant."""

    def __init__(self, symbols: BoundSymbols, handle: int) -> None:
        self._symbols = symbols
        self._handle: Optional[int] = handle

    def close(self) -> None:
        """End the portal session."""
        if self._handle is None:
            return
        _release(self._symbols, self._handle)
        self._handle = None

    def __del__(self) -> None:
        self.close()


__all__ = [
    "DEFAULT_TIMEOUT", "OEFFIS_DEVICE_ALL_DEVICES", "OEFFIS_DEVICE_DEFAULT",
    "OEFFIS_DEVICE_KEYBOARD", "OEFFIS_DEVICE_POINTER",
    "OEFFIS_DEVICE_TOUCHSCREEN", "OEFFIS_EVENT_CLOSED",
    "OEFFIS_EVENT_CONNECTED_TO_EIS", "OEFFIS_EVENT_DISCONNECTED",
    "OEFFIS_EVENT_NONE", "OeffisUnavailable", "connect_eis_fd",
    "is_available", "load_symbols",
]
