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
import os
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from je_auto_control.utils.clipboard_files import build_dropfiles
from je_auto_control.utils.exception.exceptions import AutoControlException

_WM_DROPFILES = 0x0233

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


class FileDropError(AutoControlException, RuntimeError):
    """The drop could not be delivered; a ``RuntimeError`` for older callers."""


def _declare_post_message(user32: Any) -> None:
    """Declare the user32 calls the drop makes, on the caller's private handle.

    Without argtypes ctypes marshals every argument as a 32-bit ``int``, so a
    64-bit ``HWND`` / ``WPARAM`` handle is silently truncated.
    """
    from ctypes import wintypes
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.PostMessageW.restype = wintypes.BOOL


def _default_driver(hwnd: int, blob: bytes, point: Tuple[int, int]) -> bool:
    """Post a real ``WM_DROPFILES`` to ``hwnd`` (Windows only).

    The handles are the clipboard module's private ones: declaring prototypes
    on the process-wide ``ctypes.windll`` leaked them into every other caller.
    The block belongs to the receiver only once ``PostMessage`` succeeds (the
    system marshals it across processes and ``DragFinish`` frees it), so every
    earlier failure frees it here; it used to leak on each one.
    """
    from je_auto_control.utils.clipboard.win32_clipboard_api import (
        GMEM_MOVEABLE, clipboard_api, fill_global,
    )
    try:
        user32, kernel32 = clipboard_api()
    except RuntimeError as error:
        raise FileDropError("drop_files is only supported on Windows") from error
    _declare_post_message(user32)
    # PostMessage(NULL, ...) posts to this thread's own queue and succeeds, so
    # a zero or stale hwnd reported a drop nobody received.
    if not user32.IsWindow(int(hwnd)):
        raise FileDropError(f"not a window: {hwnd!r}")
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(blob))
    if not handle:
        raise FileDropError("GlobalAlloc failed")
    try:
        fill_global(kernel32, handle, blob)
        if not user32.PostMessageW(int(hwnd), _WM_DROPFILES, handle, 0):
            raise FileDropError("PostMessage(WM_DROPFILES) failed")
    except BaseException:
        kernel32.GlobalFree(handle)
        raise
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
    # Absolute: the target resolved a relative path against its own
    # working directory.
    blob = build_dropfiles([os.path.abspath(path) if path else path for path in paths],
                           point=point, wide=wide)
    send = driver if driver is not None else _default_driver
    return bool(send(int(hwnd), blob, (int(point[0]), int(point[1]))))
