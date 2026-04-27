"""Tiny ``/dev/uinput`` wrapper used by the keyboard / mouse modules.

We deliberately avoid pulling in ``python-uinput`` as a hard dep —
the API is small enough that direct ``ctypes`` + ``ioctl`` is faster
to keep in our own tree, and it removes one optional install step
for operators. This is the same approach as the existing
``windows/interception/_dll.py`` wrapper.
"""
from __future__ import annotations

import ctypes
import errno
import os
import struct
import threading
import time
from typing import Optional

# --- Linux uinput / input-event-codes structs -------------------------------
#
# Layout cribbed from <linux/uinput.h> + <linux/input.h>. We only need
# the subset that drives a standard keyboard + relative-mouse device.

_UINPUT_MAX_NAME_SIZE = 80
_BUS_USB = 0x03

# event type codes
EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03

SYN_REPORT = 0

# relative axes
REL_X = 0x00
REL_Y = 0x01
REL_HWHEEL = 0x06
REL_WHEEL = 0x08

# mouse buttons (subset)
BTN_LEFT = 0x110
BTN_RIGHT = 0x111
BTN_MIDDLE = 0x112
BTN_SIDE = 0x113   # x1
BTN_EXTRA = 0x114  # x2

# ioctl numbers — derived from the kernel macro layout
# _IO('U', N) for write, _IOW('U', N, int) for set-bit
_UI_DEV_CREATE = 0x5501
_UI_DEV_DESTROY = 0x5502
_UI_SET_EVBIT = 0x40045564
_UI_SET_KEYBIT = 0x40045565
_UI_SET_RELBIT = 0x40045566


class _input_id(ctypes.Structure):  # noqa: N801  C struct
    _fields_ = [
        ("bustype", ctypes.c_uint16),
        ("vendor", ctypes.c_uint16),
        ("product", ctypes.c_uint16),
        ("version", ctypes.c_uint16),
    ]


class _uinput_user_dev(ctypes.Structure):  # noqa: N801  C struct
    _fields_ = [
        ("name", ctypes.c_char * _UINPUT_MAX_NAME_SIZE),
        ("id", _input_id),
        ("ff_effects_max", ctypes.c_uint32),
        ("absmax", ctypes.c_int32 * 64),
        ("absmin", ctypes.c_int32 * 64),
        ("absfuzz", ctypes.c_int32 * 64),
        ("absflat", ctypes.c_int32 * 64),
    ]


class UinputUnavailable(RuntimeError):
    """Raised when ``/dev/uinput`` can't be opened or ``ioctl`` fails."""


_libc = ctypes.CDLL("libc.so.6", use_errno=True) if os.name == "posix" else None


def _ioctl(fd: int, request: int, arg: int = 0) -> None:
    if _libc is None:
        raise UinputUnavailable("libc is unavailable on this platform")
    res = _libc.ioctl(ctypes.c_int(fd), ctypes.c_uint(request),
                      ctypes.c_int(arg))
    if res < 0:
        err = ctypes.get_errno()
        raise UinputUnavailable(
            f"ioctl {hex(request)} failed: {os.strerror(err)} ({err})"
        )


def _pack_input_event(ev_type: int, code: int, value: int) -> bytes:
    """Pack one ``input_event`` struct (16-byte timeval + 8-byte body).

    ``input_event`` lays out as ``timeval (16 bytes) + type (u16) +
    code (u16) + value (s32)`` on every glibc-flavoured Linux. We
    leave the timestamp zero — the kernel fills it in.
    """
    return struct.pack(
        "@llHHi",
        0, 0,                # tv_sec, tv_usec
        ev_type & 0xFFFF,
        code & 0xFFFF,
        value,
    )


# --- module-level singleton (lazy + lock-protected) -------------------------

_open_lock = threading.Lock()
_fd: Optional[int] = None


def _open_device() -> int:
    """Open ``/dev/uinput`` and create the synthetic combo device."""
    try:
        fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    except OSError as exc:
        raise UinputUnavailable(
            "could not open /dev/uinput. Either load the module "
            "(`sudo modprobe uinput`) or grant the user write access "
            "via udev. Underlying error: " + str(exc)
        ) from exc

    try:
        # Enable EV_KEY (keyboard + mouse buttons) and EV_REL.
        _ioctl(fd, _UI_SET_EVBIT, EV_KEY)
        _ioctl(fd, _UI_SET_EVBIT, EV_REL)
        # Mouse buttons + scroll axes.
        for btn in (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_SIDE, BTN_EXTRA):
            _ioctl(fd, _UI_SET_KEYBIT, btn)
        for axis in (REL_X, REL_Y, REL_WHEEL, REL_HWHEEL):
            _ioctl(fd, _UI_SET_RELBIT, axis)
        # Enable every key in 0..255 so the keyboard wrapper can press
        # any AC keycode without re-opening the device.
        for code in range(256):
            try:
                _ioctl(fd, _UI_SET_KEYBIT, code)
            except UinputUnavailable as exc:
                # Some kernels reject codes above the keymap; ignore
                # ENOENT / EINVAL here so the device still comes up.
                if "EINVAL" not in str(exc) and "ENOENT" not in str(exc):
                    raise

        dev = _uinput_user_dev()
        dev.name = b"AutoControl Virtual HID"
        dev.id.bustype = _BUS_USB
        dev.id.vendor = 0x16C0    # generic / "private use" Atmel range
        dev.id.product = 0x05DC
        dev.id.version = 1
        os.write(fd, bytes(dev))
        _ioctl(fd, _UI_DEV_CREATE)
        # Give udev a moment to enumerate the new device before
        # callers start writing events.
        time.sleep(0.05)
    except Exception:
        os.close(fd)
        raise
    return fd


def _ensure_fd() -> int:
    """Return the live uinput fd, opening the device on first call."""
    global _fd
    if _fd is not None:
        return _fd
    with _open_lock:
        if _fd is None:
            _fd = _open_device()
        return _fd


def is_available() -> bool:
    """Return True if ``/dev/uinput`` is openable + create-able."""
    if os.name != "posix":
        return False
    try:
        _ensure_fd()
    except UinputUnavailable:
        return False
    return True


# --- public emit helpers ----------------------------------------------------


def emit(ev_type: int, code: int, value: int, *, sync: bool = True) -> None:
    """Write one event; optionally append SYN_REPORT to commit it."""
    fd = _ensure_fd()
    os.write(fd, _pack_input_event(ev_type, code, value))
    if sync:
        os.write(fd, _pack_input_event(EV_SYN, SYN_REPORT, 0))


def emit_combo(events: list, *, sync: bool = True) -> None:
    """Write a batch of (type, code, value) events, then SYN_REPORT."""
    fd = _ensure_fd()
    for ev_type, code, value in events:
        os.write(fd, _pack_input_event(ev_type, code, value))
    if sync:
        os.write(fd, _pack_input_event(EV_SYN, SYN_REPORT, 0))


def close() -> None:
    """Tear the synthetic device down — used by tests / shutdown hooks."""
    global _fd
    with _open_lock:
        if _fd is None:
            return
        try:
            _ioctl(_fd, _UI_DEV_DESTROY)
        except UinputUnavailable:
            pass
        try:
            os.close(_fd)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise
        _fd = None


__all__ = [
    "UinputUnavailable",
    "EV_KEY", "EV_REL", "EV_SYN", "SYN_REPORT",
    "REL_X", "REL_Y", "REL_HWHEEL", "REL_WHEEL",
    "BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA",
    "close", "emit", "emit_combo", "is_available",
]
