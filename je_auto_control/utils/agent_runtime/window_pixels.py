"""Capture only an identified Windows window, with no desktop-pixel fallback."""
from __future__ import annotations

import ctypes
import sys
from contextlib import ExitStack, contextmanager
from ctypes import wintypes
from typing import Any, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


class _BitmapHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def _libraries() -> tuple[Any, Any]:
    if sys.platform != "win32":
        raise AgentTaskError("window-scoped vision capture needs a platform adapter")
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    signatures: tuple[tuple[Any, list[Any], Any], ...] = (
        (user.GetWindowRect, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        (user.IsIconic, [wintypes.HWND], wintypes.BOOL),
        (user.GetWindowDC, [wintypes.HWND], wintypes.HDC),
        (user.ReleaseDC, [wintypes.HWND, wintypes.HDC], ctypes.c_int),
        (user.PrintWindow, [wintypes.HWND, wintypes.HDC, wintypes.UINT], wintypes.BOOL),
        (gdi.CreateCompatibleDC, [wintypes.HDC], wintypes.HDC),
        (gdi.CreateCompatibleBitmap, [wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.HBITMAP),
        (gdi.SelectObject, [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ),
        (gdi.DeleteObject, [wintypes.HGDIOBJ], wintypes.BOOL),
        (gdi.DeleteDC, [wintypes.HDC], wintypes.BOOL),
        (gdi.PatBlt, [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.DWORD],
         wintypes.BOOL),
        (gdi.GetDIBits, [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                        ctypes.POINTER(_BitmapHeader), wintypes.UINT], ctypes.c_int),
    )
    for function, arguments, result in signatures:
        function.argtypes, function.restype = arguments, result
    return user, gdi


def _geometry(user: Any, hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if not hwnd or user.IsIconic(hwnd) or not user.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise AgentTaskError("owned window capture geometry is unavailable")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if not 0 < width <= 16384 or not 0 < height <= 16384 or width * height > 64_000_000:
        raise AgentTaskError("owned window capture geometry exceeds its bounded pixel budget")
    return rect.left, rect.top, width, height


def capture_window(hwnd: int) -> tuple[Any, tuple[int, int]]:
    """Render the exact window into cleared private GDI storage, retaining its desktop origin."""
    user, gdi = _libraries()
    geometry = _geometry(user, hwnd)
    x, y, width, height = geometry
    with ExitStack() as resources:
        source = user.GetWindowDC(hwnd)
        if not source:
            raise AgentTaskError("owned window device context is unavailable")
        resources.callback(user.ReleaseDC, hwnd, source)
        memory, bitmap = resources.enter_context(_surface(gdi, source, (width, height)))
        _render(user, gdi, (hwnd, memory, bitmap), (width, height))
        image = _read(gdi, memory, bitmap, (width, height))
        if geometry != _geometry(user, hwnd):
            raise AgentTaskError("owned window geometry changed during capture")
        return image, (x, y)


@contextmanager
def _surface(gdi: Any, source: int, size: tuple[int, int]) -> Iterator[tuple[int, int]]:
    memory = gdi.CreateCompatibleDC(source)
    if not memory:
        raise AgentTaskError("owned window capture context allocation failed")
    bitmap = None
    try:
        bitmap = gdi.CreateCompatibleBitmap(source, *size)
        if not bitmap:
            raise AgentTaskError("owned window capture bitmap allocation failed")
        yield memory, bitmap
    finally:
        # Delete the private DC first even if restoring its selected object failed.
        gdi.DeleteDC(memory)
        if bitmap:
            gdi.DeleteObject(bitmap)


def _render(user: Any, gdi: Any, handles: tuple[int, int, int], size: tuple[int, int]) -> None:
    hwnd, memory, bitmap = handles
    previous = gdi.SelectObject(memory, bitmap)
    if not previous or previous == ctypes.c_void_p(-1).value:
        raise AgentTaskError("owned window capture bitmap selection failed")
    try:
        if not gdi.PatBlt(memory, 0, 0, *size, 0x00000042):  # BLACKNESS, never uninitialized pixels.
            raise AgentTaskError("owned window capture buffer could not be cleared")
        if not user.PrintWindow(hwnd, memory, 2):  # PW_RENDERFULLCONTENT, no screen/BitBlt fallback.
            raise AgentTaskError("owned window render is unavailable")
    finally:
        if not gdi.SelectObject(memory, previous):
            raise AgentTaskError("owned window capture bitmap could not be deselected")


def _read(gdi: Any, memory: int, bitmap: int, size: tuple[int, int]) -> Any:
    from PIL import Image
    width, height = size
    header = _BitmapHeader()
    header.biSize, header.biWidth, header.biHeight = ctypes.sizeof(header), width, -height
    header.biPlanes, header.biBitCount = 1, 32
    data = ctypes.create_string_buffer(width * height * 4)
    # GetDIBits requires the bitmap to be deselected; _render restores it before this call.
    if gdi.GetDIBits(memory, bitmap, 0, height, data, ctypes.byref(header), 0) != height:
        raise AgentTaskError("owned window pixels could not be read completely")
    return Image.frombytes("RGB", size, data.raw, "raw", "BGRX")
