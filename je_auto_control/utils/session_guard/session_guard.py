"""Guard against driving input into a locked / non-interactive session.

Unattended runs silently fail when the workstation is locked or the RDP
session is disconnected: ``SetCursorPos`` / clicks no-op or throw, and the
script produces phantom input. Check first and fail with a clear error
instead. On Windows the probe opens the input desktop (which fails when
the station is locked); other platforms report "not locked" unless a
custom probe is supplied. The probe is injectable for tests. Imports no
``PySide6``.
"""
import sys
from typing import Callable, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException

LockProbe = Callable[[], bool]


def _windows_locked() -> bool:
    """True when the Windows input desktop can't be opened (station locked)."""
    import ctypes
    _DESKTOP_READOBJECTS = 0x0001
    user32 = ctypes.windll.user32  # nosec B607  # reason: fixed system DLL
    handle = user32.OpenInputDesktop(0, False, _DESKTOP_READOBJECTS)
    if not handle:
        return True
    user32.CloseDesktop(handle)
    return False


def _default_probe() -> bool:
    """Best-effort lock detection; only implemented on Windows."""
    if sys.platform in ("win32", "cygwin", "msys"):
        try:
            return _windows_locked()
        except (OSError, AttributeError):
            return False
    return False


def is_session_locked(probe: Optional[LockProbe] = None) -> bool:
    """Return True when the interactive session appears locked / unavailable."""
    return bool((probe or _default_probe)())


def ensure_interactive_session(probe: Optional[LockProbe] = None) -> bool:
    """Raise :class:`AutoControlException` when the session is locked.

    Returns True when interactive, so it can gate an unattended flow before
    it emits phantom clicks into a locked screen.
    """
    if is_session_locked(probe):
        raise AutoControlException(
            "session is locked or non-interactive; input would be lost",
        )
    return True
