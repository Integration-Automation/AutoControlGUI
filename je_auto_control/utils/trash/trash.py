"""Move files to the OS recycle bin / trash instead of deleting them.

Makes destructive operations recoverable: a "deleted" file lands in the
Windows Recycle Bin / macOS Trash / Linux XDG trash, where it can be
restored — answering "the recycle bin and undo don't work" for app file
deletions. Prefers ``send2trash`` when installed (correct cross-platform
behaviour) and falls back to the Win32 Recycle Bin via ``SHFileOperation``
with the undo flag. It never deletes permanently here; callers that truly
want that should use ``Path.unlink``. The backend is injectable so the
dispatch is unit-testable without touching a real recycle bin.
"""
import sys
from pathlib import Path
from typing import Callable, Optional, Union

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

TrashBackend = Callable[[str], None]


def _send2trash_backend() -> Optional[TrashBackend]:
    try:
        from send2trash import send2trash
    except ImportError:
        return None
    return send2trash


def _win32_recycle(path: str) -> None:
    """Send ``path`` to the Windows Recycle Bin via SHFileOperation."""
    import ctypes
    from ctypes import wintypes

    class _SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    fo_delete = 3
    flags = 0x40 | 0x10 | 0x4  # ALLOWUNDO | NOCONFIRMATION | SILENT
    operation = _SHFILEOPSTRUCTW()
    operation.wFunc = fo_delete
    operation.pFrom = path + "\0\0"  # the path list is double-null terminated
    operation.fFlags = flags
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise OSError(f"SHFileOperation failed ({result}) for {path!r}")


def _select_backend() -> Optional[TrashBackend]:
    backend = _send2trash_backend()
    if backend is not None:
        return backend
    if sys.platform == "win32":
        return _win32_recycle
    return None


def move_to_trash(path: Union[str, Path], *,
                  backend: Optional[TrashBackend] = None) -> bool:
    """Move ``path`` to the OS recycle bin / trash. Return ``True`` on success.

    Raises :class:`FileNotFoundError` if the path is missing, or
    :class:`RuntimeError` when no trash backend is available (install
    ``send2trash`` for macOS / Linux).
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(str(path))
    chosen = backend or _select_backend()
    if chosen is None:
        raise RuntimeError(
            "no recycle-bin backend available; pip install send2trash",
        )
    chosen(str(target.resolve()))
    autocontrol_logger.info("moved to trash: %s", target)
    return True
