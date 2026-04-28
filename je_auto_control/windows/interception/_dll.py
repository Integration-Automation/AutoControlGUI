"""Lazy ctypes loader + Structures for ``interception.dll``.

We do **not** require the DLL at import time — picking up
``import je_auto_control`` on a machine without the driver should not
explode. :func:`load_context` performs the actual load on demand and
raises :class:`InterceptionUnavailable` with an explanatory message
when anything is missing, letting the platform wrapper fall back to
``SendInput`` cleanly.
"""
from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes
from typing import Optional


class InterceptionUnavailable(RuntimeError):
    """Raised when ``interception.dll`` or the kernel driver is missing."""


# --- C structs ---------------------------------------------------------------


class InterceptionKeyStroke(ctypes.Structure):
    """Keyboard stroke as defined in ``interception.h``."""

    _fields_ = [
        ("code", ctypes.c_ushort),         # Set-1 scancode
        ("state", ctypes.c_ushort),        # bit flags below
        ("information", ctypes.c_uint),    # reserved / driver-specific
    ]


class InterceptionMouseStroke(ctypes.Structure):
    """Mouse stroke as defined in ``interception.h``."""

    _fields_ = [
        ("state", ctypes.c_ushort),        # button-flags bitmap
        ("flags", ctypes.c_ushort),        # MOVE_RELATIVE / _ABSOLUTE / etc.
        ("rolling", ctypes.c_short),       # wheel delta (signed)
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("information", ctypes.c_uint),
    ]


# --- key state flags ---------------------------------------------------------

KEY_DOWN = 0x00
KEY_UP = 0x01
KEY_E0 = 0x02     # extended scancode prefix
KEY_E1 = 0x04     # extended scancode prefix (rare; Pause key)

# --- mouse flags / state -----------------------------------------------------

MOUSE_MOVE_RELATIVE = 0x000
MOUSE_MOVE_ABSOLUTE = 0x001
MOUSE_VIRTUAL_DESKTOP = 0x002
MOUSE_ATTRIBUTES_CHANGED = 0x004

MOUSE_LEFT_DOWN = 0x001
MOUSE_LEFT_UP = 0x002
MOUSE_RIGHT_DOWN = 0x004
MOUSE_RIGHT_UP = 0x008
MOUSE_MIDDLE_DOWN = 0x010
MOUSE_MIDDLE_UP = 0x020
MOUSE_BUTTON4_DOWN = 0x040
MOUSE_BUTTON4_UP = 0x080
MOUSE_BUTTON5_DOWN = 0x100
MOUSE_BUTTON5_UP = 0x200
MOUSE_WHEEL = 0x400


# --- module-level singletons (lazy-init, double-checked) ---------------------

_load_lock = threading.Lock()
_dll: Optional[ctypes.CDLL] = None
_context = None  # InterceptionContext (opaque pointer)


def _resolve_dll_path() -> str:
    """Pick the DLL path: explicit env var first, then PATH, then bundled."""
    explicit = os.environ.get("JE_AUTOCONTROL_INTERCEPTION_DLL")
    if explicit:
        return explicit
    return "interception.dll"


def _load_dll() -> ctypes.CDLL:
    """Load and prototype ``interception.dll``."""
    path = _resolve_dll_path()
    try:
        dll = ctypes.WinDLL(path)
    except OSError as exc:
        raise InterceptionUnavailable(
            f"could not load {path!r}: {exc}. Install the driver from "
            "https://github.com/oblitum/Interception or set "
            "JE_AUTOCONTROL_INTERCEPTION_DLL to its full path."
        ) from exc

    # Prototype the few functions we actually call. The full API has
    # filter / wait / receive helpers used for hooking — we only inject.
    dll.interception_create_context.restype = ctypes.c_void_p
    dll.interception_create_context.argtypes = []

    dll.interception_destroy_context.restype = None
    dll.interception_destroy_context.argtypes = [ctypes.c_void_p]

    dll.interception_send.restype = ctypes.c_int
    dll.interception_send.argtypes = [
        ctypes.c_void_p,          # context
        ctypes.c_int,             # device id
        ctypes.c_void_p,          # stroke pointer
        ctypes.c_uint,            # n strokes
    ]

    dll.interception_is_keyboard.restype = ctypes.c_int
    dll.interception_is_keyboard.argtypes = [ctypes.c_int]

    dll.interception_is_mouse.restype = ctypes.c_int
    dll.interception_is_mouse.argtypes = [ctypes.c_int]
    return dll


def _create_context(dll: ctypes.CDLL) -> ctypes.c_void_p:
    """Open a driver context; raise if the kernel side is missing."""
    ctx = dll.interception_create_context()
    if not ctx:
        raise InterceptionUnavailable(
            "interception_create_context returned NULL — the kernel "
            "driver is most likely not installed or the service is "
            "stopped. Run install-interception.exe as Administrator "
            "and reboot."
        )
    return ctypes.c_void_p(ctx)


def is_available() -> bool:
    """Return True if both DLL and driver context are reachable.

    Cheap check used by the wrapper's backend selector — it does *not*
    keep the context open after the probe.
    """
    try:
        load_context()
    except InterceptionUnavailable:
        return False
    return True


def load_context() -> tuple[ctypes.CDLL, ctypes.c_void_p]:
    """Return ``(dll, context)`` lazily — opened once per process."""
    global _dll, _context
    if _dll is not None and _context is not None:
        return _dll, _context
    with _load_lock:
        if _dll is None:
            _dll = _load_dll()
        if _context is None:
            _context = _create_context(_dll)
        return _dll, _context


# --- helpers used by the keyboard / mouse modules ---------------------------


_DEFAULT_KEYBOARD_DEVICE = 1
_DEFAULT_MOUSE_DEVICE = 11


def default_keyboard_device() -> int:
    """Driver device id used when injecting keyboard strokes."""
    return int(
        os.environ.get(
            "JE_AUTOCONTROL_INTERCEPTION_KEYBOARD",
            _DEFAULT_KEYBOARD_DEVICE,
        )
    )


def default_mouse_device() -> int:
    """Driver device id used when injecting mouse strokes."""
    return int(
        os.environ.get(
            "JE_AUTOCONTROL_INTERCEPTION_MOUSE",
            _DEFAULT_MOUSE_DEVICE,
        )
    )


# --- vk → scancode helper ---------------------------------------------------

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.MapVirtualKeyW.restype = wintypes.UINT
_user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]

_MAPVK_VK_TO_VSC_EX = 4   # returns the extended-scancode-prefixed value


def vk_to_scancode(vk_code: int) -> tuple[int, bool]:
    """Resolve a Win32 VK code to ``(scancode, is_extended)``.

    The Interception driver wants Set-1 scancodes; ``MapVirtualKeyW``
    with ``MAPVK_VK_TO_VSC_EX`` returns the high byte set to ``0xE0``
    when the key needs the extended prefix (arrow keys, numeric pad
    enter, etc.). We split that into ``(low_byte, extended_bool)``
    so the caller can choose ``KEY_E0``.
    """
    raw = int(_user32.MapVirtualKeyW(int(vk_code), _MAPVK_VK_TO_VSC_EX))
    is_extended = (raw & 0xE000) == 0xE000
    return raw & 0x00FF, is_extended


__all__ = [
    "InterceptionUnavailable",
    "InterceptionKeyStroke",
    "InterceptionMouseStroke",
    "KEY_DOWN", "KEY_UP", "KEY_E0", "KEY_E1",
    "MOUSE_MOVE_RELATIVE", "MOUSE_MOVE_ABSOLUTE", "MOUSE_VIRTUAL_DESKTOP",
    "MOUSE_LEFT_DOWN", "MOUSE_LEFT_UP",
    "MOUSE_RIGHT_DOWN", "MOUSE_RIGHT_UP",
    "MOUSE_MIDDLE_DOWN", "MOUSE_MIDDLE_UP",
    "MOUSE_BUTTON4_DOWN", "MOUSE_BUTTON4_UP",
    "MOUSE_BUTTON5_DOWN", "MOUSE_BUTTON5_UP",
    "MOUSE_WHEEL",
    "default_keyboard_device", "default_mouse_device",
    "is_available", "load_context", "vk_to_scancode",
]
