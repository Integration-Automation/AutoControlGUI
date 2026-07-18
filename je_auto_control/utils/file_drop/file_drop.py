"""Drop files onto a window (Windows ``WM_DROPFILES``).

``clipboard_files`` *stages* a file-drop list on the clipboard so a user can
``Ctrl+V`` it; this module actively **drops** files onto a target window — the
completion of a drag-and-drop — by posting a ``WM_DROPFILES`` message carrying a
``DROPFILES`` blob. It reuses ``clipboard_files.build_dropfiles`` to pack that
blob (so the byte layout is shared, not re-implemented) and dispatches it through
an injectable *driver* seam, so the build-and-dispatch logic is unit-testable on
any platform by passing a fake driver; the real ``GlobalAlloc`` + ``PostMessage``
lives in the default Win32 driver. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from je_auto_control.utils.clipboard_files import build_dropfiles

_WM_DROPFILES = 0x0233
_GMEM_MOVEABLE = 0x0002

# A driver dispatches a packed DROPFILES blob to a window: (hwnd, blob, point) -> bool.
DropDriver = Callable[[int, bytes, Tuple[int, int]], bool]


def plan_file_drop(paths: Sequence[str], *, point: Tuple[int, int] = (0, 0),
                   wide: bool = True) -> Dict[str, Any]:
    """Build the ``WM_DROPFILES`` payload for dropping ``paths`` (pure, no send).

    Returns ``{message, paths, point, wide, blob_size}`` — a dry-run description
    that reuses the same :func:`build_dropfiles` packing the real drop sends.
    """
    blob = build_dropfiles(paths, point=point, wide=wide)
    return {"message": _WM_DROPFILES, "paths": [str(p) for p in paths],
            "point": [int(point[0]), int(point[1])], "wide": bool(wide),
            "blob_size": len(blob)}


def _declare_win32_signatures(kernel32: Any, user32: Any) -> None:
    """Declare argtypes/restypes so 64-bit handles aren't truncated.

    Without argtypes ctypes marshals every argument as a 32-bit ``int``, so a
    64-bit ``HGLOBAL`` / ``WPARAM`` is silently truncated — ``GlobalLock`` then
    receives a bogus handle, returns ``NULL``, and ``memmove(NULL, ...)`` faults.
    """
    import ctypes
    from ctypes import wintypes
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.PostMessageW.restype = wintypes.BOOL


def _default_driver(hwnd: int, blob: bytes, point: Tuple[int, int]) -> bool:
    """Post a real ``WM_DROPFILES`` to ``hwnd`` (Windows only)."""
    import sys
    if not sys.platform.startswith("win"):
        raise RuntimeError("drop_files is only supported on Windows")
    import ctypes
    kernel32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
    _declare_win32_signatures(kernel32, user32)
    handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(blob))
    if not handle:
        raise RuntimeError("GlobalAlloc failed")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        raise RuntimeError("GlobalLock failed")
    ctypes.memmove(pointer, blob, len(blob))
    kernel32.GlobalUnlock(handle)
    # The receiving window owns the memory and frees it via DragFinish.
    if not user32.PostMessageW(int(hwnd), _WM_DROPFILES, handle, 0):
        raise RuntimeError("PostMessage(WM_DROPFILES) failed")
    return True


def drop_files(hwnd: int, paths: Sequence[str], *,
               point: Tuple[int, int] = (0, 0), wide: bool = True,
               driver: Optional[DropDriver] = None) -> bool:
    """Drop ``paths`` onto window ``hwnd`` via ``WM_DROPFILES``; True on success.

    ``point`` is the drop coordinate in the window's client area. Pass a
    ``driver`` ``(hwnd, blob, point) -> bool`` to intercept the send (e.g. in
    tests); the default driver posts the real Windows message.
    """
    if not paths:
        raise ValueError("at least one path is required")
    blob = build_dropfiles(paths, point=point, wide=wide)
    send = driver if driver is not None else _default_driver
    return bool(send(int(hwnd), blob, (int(point[0]), int(point[1]))))
