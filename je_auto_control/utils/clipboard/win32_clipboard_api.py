"""Win32 clipboard prototypes and the open/alloc/lock dance, declared once.

Every clipboard format — text, image, HTML, RTF, CSV, file drops — goes through
the same four Win32 calls, and every module that reimplemented them got the same
detail wrong: ``argtypes``. A memory handle is pointer-width, ctypes defaults an
undeclared parameter to ``c_int``, and so ``GlobalLock(handle)`` raises
``OverflowError: int too long to convert`` for any real handle on 64-bit
Windows. Declaring only ``restype`` fixes the value coming *back* and leaves the
argument going *in* broken, which is exactly what three modules did — their
``set_clipboard_*`` functions failed on every single call.

Handles are private (``WinDLL``, not the process-wide cached ``windll``):
prototypes live on the function objects, so a shared handle would leak these
declarations into every other user32 caller in the process.
"""
import ctypes
import sys
from ctypes import wintypes
from typing import Optional, Tuple

GMEM_MOVEABLE = 0x0002
_OPEN_FAILED = "OpenClipboard failed"


def _require_windows() -> None:
    if not sys.platform.startswith("win"):
        raise RuntimeError("the Win32 clipboard API is only available on Windows")


def clipboard_api() -> Tuple[object, object]:
    """``(user32, kernel32)`` with every clipboard prototype declared."""
    _require_windows()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
    user32.EnumClipboardFormats.restype = wintypes.UINT
    user32.GetClipboardFormatNameW.argtypes = [wintypes.UINT, wintypes.LPWSTR,
                                               ctypes.c_int]
    user32.GetClipboardFormatNameW.restype = ctypes.c_int
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    return user32, kernel32


def register_format(name: str) -> int:
    """Register (or look up) a named clipboard format id."""
    user32, _kernel32 = clipboard_api()
    return int(user32.RegisterClipboardFormatW(name))


def set_clipboard_format(format_id: int, payload: bytes, *,
                         empty_first: bool = True) -> None:
    """Put raw bytes on the clipboard under ``format_id``.

    The buffer is allocated and filled *before* the clipboard is opened, so a
    failure part-way leaves the user's clipboard untouched rather than emptied.
    On success the clipboard owns the handle and must not free it here.
    """
    user32, kernel32 = clipboard_api()
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
    if not handle:
        raise RuntimeError("GlobalAlloc failed")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        raise RuntimeError("GlobalLock failed")
    ctypes.memmove(pointer, payload, len(payload))
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        raise RuntimeError(_OPEN_FAILED)
    try:
        if empty_first:
            user32.EmptyClipboard()
        if not user32.SetClipboardData(int(format_id), handle):
            raise RuntimeError(f"SetClipboardData({format_id}) failed")
    finally:
        user32.CloseClipboard()


def get_clipboard_format(format_id: int) -> Optional[bytes]:
    """Read the clipboard's ``format_id`` payload, or ``None`` when absent."""
    user32, kernel32 = clipboard_api()
    if not user32.OpenClipboard(None):
        raise RuntimeError(_OPEN_FAILED)
    try:
        handle = user32.GetClipboardData(int(format_id))
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.string_at(pointer, kernel32.GlobalSize(handle))
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
