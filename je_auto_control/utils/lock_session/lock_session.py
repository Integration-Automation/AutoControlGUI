"""Lock the workstation, wait for it to be unlocked, and classify transitions.

:mod:`session_guard` answers "is the session locked right now?" and raises if it
is. The missing half is *acting* on the lock state: lock the machine at the end
of an unattended run, block until a human unlocks it before resuming, or reduce
a stream of lock-state samples to lock / unlock events. ``lock_session`` adds:

* :func:`lock_session` — lock the workstation now (``LockWorkStation`` on
  Windows, ``loginctl lock-session`` / ``CGSession -suspend`` elsewhere),
  through an injectable ``driver`` seam.
* :func:`plan_lock_session` — pure planner describing how the lock would be
  performed on this OS, and whether a default is available.
* :func:`wait_for_unlock` / :func:`wait_for_lock` — poll
  :func:`session_guard.is_session_locked` until the state flips or a timeout,
  with injectable ``clock`` / ``sleep`` / ``probe`` for deterministic tests.
* :func:`classify_lock_transitions` — pure: a list of lock-state samples to a
  list of ``{event, locked}`` lock / unlock transitions.

Imports no ``PySide6``.
"""
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from je_auto_control.utils.session_guard import is_session_locked
from je_auto_control.utils.session_guard.session_guard import LockProbe

# A driver performs the lock and returns whether it succeeded.
LockDriver = Callable[[], bool]


def _win_lock() -> bool:
    """Lock the Windows workstation via ``LockWorkStation``."""
    import ctypes
    user32 = ctypes.windll.user32  # nosec B607  # reason: fixed system DLL
    return bool(user32.LockWorkStation())


def _lock_backend() -> str:
    """Return the lock backend name for the current platform."""
    if sys.platform.startswith("win"):
        return "LockWorkStation"
    if sys.platform == "darwin":
        return "CGSession"
    return "loginctl"


_CGSESSION = ("/System/Library/CoreServices/Menu Extras/"
              "User.menu/Contents/Resources/CGSession")


def _lock_argv(backend: str) -> Optional[List[str]]:
    """Return the fixed argv for a subprocess lock backend, or None."""
    if backend == "loginctl":
        return ["loginctl", "lock-session"]
    if backend == "CGSession":
        return [_CGSESSION, "-suspend"]
    return None


def plan_lock_session() -> Dict[str, Any]:
    """Describe how the workstation would be locked on this OS (pure).

    Returns ``{backend, argv, available}``. ``available`` is ``True`` when this
    platform has a built-in default; otherwise :func:`lock_session` needs an
    explicit ``driver=``.
    """
    backend = _lock_backend()
    argv = _lock_argv(backend)
    available = backend == "LockWorkStation" or argv is not None
    return {"backend": backend, "argv": argv, "available": available}


def _run_argv(argv: List[str]) -> bool:
    """Run a fixed lock argv and report success (no shell)."""
    import subprocess  # nosec B404  # reason: fixed argv, no shell
    completed = subprocess.run(argv, check=False)  # nosec B603  # nosemgrep
    return completed.returncode == 0


def _default_driver() -> LockDriver:
    """Return the OS lock driver, or raise if none is available."""
    backend = _lock_backend()
    if backend == "LockWorkStation":
        return _win_lock
    argv = _lock_argv(backend)
    if argv is not None:
        return lambda: _run_argv(argv)
    raise RuntimeError(
        "lock_session has no OS driver on this platform; pass driver=")


def lock_session(*, driver: Optional[LockDriver] = None) -> bool:
    """Lock the workstation now; return whether the lock was requested.

    Pass ``driver`` (a ``() -> bool``) to intercept the OS call in tests; the
    default locks via the platform backend from :func:`plan_lock_session`.
    """
    acquire = driver if driver is not None else _default_driver()
    return bool(acquire())


def _wait_lock_state(target_locked: bool, *, probe: Optional[LockProbe],
                     timeout_s: float, interval_s: float,
                     clock: Callable[[], float],
                     sleep: Callable[[float], None]) -> bool:
    """Poll until the lock state equals ``target_locked`` or timeout."""
    deadline = clock() + float(timeout_s)
    while True:
        if bool(is_session_locked(probe)) == target_locked:
            return True
        if clock() >= deadline:
            return False
        sleep(float(interval_s))


def wait_for_unlock(*, probe: Optional[LockProbe] = None,
                    timeout_s: float = 30.0, interval_s: float = 0.5,
                    clock: Callable[[], float] = time.monotonic,
                    sleep: Callable[[float], None] = time.sleep) -> bool:
    """Block until the session is unlocked; return ``True``, or ``False`` on timeout.

    Reuses :func:`session_guard.is_session_locked` (Windows default probe).
    ``clock`` / ``sleep`` / ``probe`` are injectable for deterministic tests.
    """
    return _wait_lock_state(False, probe=probe, timeout_s=timeout_s,
                            interval_s=interval_s, clock=clock, sleep=sleep)


def wait_for_lock(*, probe: Optional[LockProbe] = None,
                  timeout_s: float = 30.0, interval_s: float = 0.5,
                  clock: Callable[[], float] = time.monotonic,
                  sleep: Callable[[float], None] = time.sleep) -> bool:
    """Block until the session is locked; return ``True``, or ``False`` on timeout."""
    return _wait_lock_state(True, probe=probe, timeout_s=timeout_s,
                            interval_s=interval_s, clock=clock, sleep=sleep)


def classify_lock_transitions(states: Sequence[bool]) -> List[Dict[str, Any]]:
    """Reduce lock-state samples to lock / unlock transitions (pure).

    Each adjacent ``False -> True`` yields a ``lock`` event and each
    ``True -> False`` an ``unlock`` event; unchanged samples yield nothing.
    """
    events: List[Dict[str, Any]] = []
    previous: Optional[bool] = None
    for sample in states:
        current = bool(sample)
        if previous is not None and current != previous:
            kind = "lock" if current else "unlock"
            events.append({"event": kind, "locked": current})
        previous = current
    return events
