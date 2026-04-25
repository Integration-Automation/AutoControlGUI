"""Headless image clipboard helpers.

Reads work via Pillow's ``ImageGrab.grabclipboard`` on every supported
platform (Windows, macOS, Linux with xclip). Writes are
Windows-only today: macOS and Linux callers receive a clear
``NotImplementedError`` so the higher-level MCP tool can surface the
limitation in its result instead of crashing.
"""
import io
import os
import sys
from typing import Optional


def get_clipboard_image() -> Optional[bytes]:
    """Return the current clipboard image as PNG bytes, or ``None`` if empty."""
    from PIL import ImageGrab
    try:
        image = ImageGrab.grabclipboard()
    except (OSError, NotImplementedError):
        return None
    if image is None:
        return None
    if isinstance(image, list):
        # On macOS / Linux the clipboard may carry file paths instead of an image.
        return None
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def set_clipboard_image(image_path: str) -> None:
    """Place ``image_path`` (any Pillow-readable file) onto the clipboard."""
    safe_path = os.path.realpath(os.fspath(image_path))
    if not os.path.isfile(safe_path):
        raise FileNotFoundError(f"image not found: {safe_path}")
    if sys.platform.startswith("win"):
        _win_set_image(safe_path)
        return
    raise NotImplementedError(
        f"set_clipboard_image is currently only implemented on Windows "
        f"(got {sys.platform})"
    )


def _win_set_image(path: str) -> None:
    """Win32 implementation: copy a Pillow-rendered DIB onto the clipboard."""
    import ctypes
    from ctypes import wintypes
    from PIL import Image

    image = Image.open(path).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="BMP")
    # Strip the 14-byte BITMAPFILEHEADER — clipboard wants raw DIB.
    dib_payload = buffer.getvalue()[14:]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    cf_dib = 8
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

    handle = kernel32.GlobalAlloc(gmem_moveable, len(dib_payload))
    if not handle:
        raise RuntimeError("GlobalAlloc failed for clipboard image")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        raise RuntimeError("GlobalLock failed for clipboard image")
    ctypes.memmove(pointer, dib_payload, len(dib_payload))
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(cf_dib, handle):
            raise RuntimeError("SetClipboardData failed for clipboard image")
    finally:
        user32.CloseClipboard()


__all__ = ["get_clipboard_image", "set_clipboard_image"]
