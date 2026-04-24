"""Headless cross-platform text clipboard.

Windows uses Win32 clipboard API via ctypes.
macOS shells out to pbcopy / pbpaste.
Linux shells out to xclip or xsel (whichever is available).

All functions raise ``RuntimeError`` if the platform backend is missing so
callers can degrade gracefully.
"""
import shutil
import subprocess  # nosec B404  # reason: required for pbcopy/pbpaste/xclip/xsel
import sys
from typing import Optional


def get_clipboard() -> str:
    """Return the current clipboard text (empty string if empty)."""
    if sys.platform.startswith("win"):
        return _win_get()
    if sys.platform == "darwin":
        return _mac_get()
    return _linux_get()


def set_clipboard(text: str) -> None:
    """Replace clipboard contents with ``text``."""
    if not isinstance(text, str):
        raise TypeError("set_clipboard expects a str")
    if sys.platform.startswith("win"):
        _win_set(text)
        return
    if sys.platform == "darwin":
        _mac_set(text)
        return
    _linux_set(text)


# === Windows backend =========================================================

def _win_get() -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    cf_unicodetext = 13

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    if not user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        handle = user32.GetClipboardData(cf_unicodetext)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _win_set(text: str) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    cf_unicodetext = 13
    gmem_moveable = 0x0002

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    handle = kernel32.GlobalAlloc(gmem_moveable, size)
    if not handle:
        raise RuntimeError("GlobalAlloc failed")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        raise RuntimeError("GlobalLock failed")
    ctypes.memmove(pointer, ctypes.addressof(data), size)
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(cf_unicodetext, handle):
            raise RuntimeError("SetClipboardData failed")
    finally:
        user32.CloseClipboard()


# === macOS backend ===========================================================

def _mac_get() -> str:
    result = subprocess.run(  # nosec B603 B607  # reason: hard-coded macOS clipboard tool, argv list
        ["pbpaste"], capture_output=True, check=True, timeout=5,
    )
    return result.stdout.decode("utf-8", errors="replace")


def _mac_set(text: str) -> None:
    subprocess.run(  # nosec B603 B607  # reason: hard-coded macOS clipboard tool, argv list
        ["pbcopy"], input=text.encode("utf-8"),
        check=True, timeout=5,
    )


# === Linux backend ===========================================================

def _linux_cmd() -> Optional[list]:
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    if shutil.which("xsel"):
        return ["xsel", "--clipboard"]
    return None


def _linux_get() -> str:
    cmd = _linux_cmd()
    if cmd is None:
        raise RuntimeError("Install xclip or xsel for Linux clipboard support")
    read_cmd = cmd + ["-o"] if cmd[0] == "xclip" else cmd + ["--output"]
    result = subprocess.run(  # nosec B603  # reason: argv from allowlist (xclip/xsel) discovered via shutil.which
        read_cmd, capture_output=True, check=True, timeout=5,
    )
    return result.stdout.decode("utf-8", errors="replace")


def _linux_set(text: str) -> None:
    cmd = _linux_cmd()
    if cmd is None:
        raise RuntimeError("Install xclip or xsel for Linux clipboard support")
    write_cmd = cmd + ["-i"] if cmd[0] == "xclip" else cmd + ["--input"]
    subprocess.run(  # nosec B603  # reason: argv from allowlist (xclip/xsel) discovered via shutil.which
        write_cmd, input=text.encode("utf-8"),
        check=True, timeout=5,
    )
