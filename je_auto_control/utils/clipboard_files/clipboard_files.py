"""Clipboard file-drop list (Windows ``CF_HDROP`` / ``DROPFILES``).

The clipboard layer carries text and images, and ``rich_clipboard`` added HTML, but the
framework could never put a *list of files* on the clipboard — the thing Explorer reads
when you copy files and ``Ctrl+V`` them elsewhere (a ``CF_HDROP`` drop). Building that
blob is fiddly byte work: a fixed ``DROPFILES`` header followed by a double-null-terminated
(optionally wide) path list, with the header's ``pFiles`` offset pointing at the list.

This isolates that error-prone packing into pure, fully unit-testable ``build_dropfiles`` /
``parse_dropfiles`` byte functions (no device needed), with thin Windows-only
``set_clipboard_files`` / ``get_clipboard_files`` wrappers on top — the same split
``rich_clipboard`` uses for ``CF_HTML``. The pure functions import no ``PySide6`` and run
on any platform; only the clipboard wrappers touch Win32.
"""
import struct
from typing import Any, Dict, List, Optional, Sequence, Tuple

_CF_HDROP = 15
_GMEM_MOVEABLE = 0x0002
_HEADER_SIZE = 20  # DROPFILES: pFiles + pt.x + pt.y + fNC + fWide (5 x DWORD)


def build_dropfiles(paths: Sequence[str], *, point: Tuple[int, int] = (0, 0),
                    wide: bool = True, non_client: bool = False) -> bytes:
    """Pack ``paths`` into a ``CF_HDROP`` / ``DROPFILES`` byte blob.

    ``point`` is the drop coordinate, ``wide`` selects UTF-16LE (the modern default)
    over single-byte paths, and ``non_client`` sets the ``fNC`` flag. The path list is
    double-null terminated as the format requires.
    """
    if not paths:
        raise ValueError("at least one path is required")
    header = struct.pack("<5I", _HEADER_SIZE, int(point[0]), int(point[1]),
                         1 if non_client else 0, 1 if wide else 0)
    listing = "".join(f"{path}\0" for path in paths) + "\0"
    body = listing.encode("utf-16-le" if wide else "latin-1")
    return header + body


def parse_dropfiles(data: bytes) -> Dict[str, Any]:
    """Unpack a ``CF_HDROP`` / ``DROPFILES`` blob into ``{paths, point, wide, non_client}``."""
    if len(data) < _HEADER_SIZE:
        raise ValueError("data too short for a DROPFILES header")
    p_files, x, y, f_nc, f_wide = struct.unpack("<5I", data[:_HEADER_SIZE])
    wide = bool(f_wide)
    body = data[p_files:]
    text = body.decode("utf-16-le" if wide else "latin-1")
    paths = [part for part in text.split("\0") if part]
    return {"paths": paths, "point": [x, y], "wide": wide,
            "non_client": bool(f_nc)}


def set_clipboard_files(paths: Sequence[str], *, point: Tuple[int, int] = (0, 0),
                        non_client: bool = False) -> None:
    """Put ``paths`` on the clipboard as a ``CF_HDROP`` file-drop list (Windows)."""
    blob = build_dropfiles(paths, point=point, wide=True, non_client=non_client)
    _win_set_hdrop(blob)


def get_clipboard_files() -> Optional[List[str]]:
    """Return the file paths on the clipboard as a ``CF_HDROP`` list, or ``None``."""
    blob = _win_get_hdrop()
    if blob is None:
        return None
    return parse_dropfiles(blob)["paths"]


def _win_set_hdrop(blob: bytes) -> None:
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.restype = ctypes.c_void_p
    if not user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(blob))
        if not handle:
            raise RuntimeError("GlobalAlloc failed")
        pointer = kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, blob, len(blob))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(_CF_HDROP, handle):
            raise RuntimeError("SetClipboardData(CF_HDROP) failed")
    finally:
        user32.CloseClipboard()


def _win_get_hdrop() -> Optional[bytes]:
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.restype = ctypes.c_void_p
    if not user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        handle = user32.GetClipboardData(_CF_HDROP)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        size = kernel32.GlobalSize(handle)
        data = ctypes.string_at(pointer, size)
        kernel32.GlobalUnlock(handle)
        return data
    finally:
        user32.CloseClipboard()
