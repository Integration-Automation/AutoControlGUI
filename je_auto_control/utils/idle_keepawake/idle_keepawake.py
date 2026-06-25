"""Detect how long the user has been idle, and keep the machine awake.

Long unattended automation runs get derailed two ways: the screensaver / power
policy sleeps the box mid-run, or the run should hold while a human is actively
using the machine. The framework had neither signal. ``idle_keepawake`` adds
both, behind injectable seams so all logic is testable without touching the OS:

* :func:`idle_seconds` / :func:`is_idle` report seconds since the last user
  keyboard / mouse input (``GetLastInputInfo`` on Windows) through an injectable
  ``probe``.
* :func:`plan_keep_awake` is a pure planner describing which wake flags a request
  maps to. :func:`keep_awake` is a scoped context manager, and
  :func:`keep_awake_on` / :func:`allow_sleep` are a process-global on / off pair
  for JSON action flows — both apply the plan through an injectable ``driver``
  (``SetThreadExecutionState`` / ``caffeinate`` / ``systemd-inhibit`` by
  default) and restore the prior state on release.

Imports no ``PySide6``.
"""
import ctypes
import sys
import threading
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional

# Windows SetThreadExecutionState flags.
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002

# A probe: returns seconds since the last user input.
IdleProbe = Callable[[], float]
# A driver: applies a keep-awake plan and returns a zero-arg release callable.
KeepAwakeDriver = Callable[[Dict[str, Any]], Callable[[], None]]

# Process-global keep-awake state for the on / off serializable surface: holds
# the active release callable (0 or 1 entry), swapped atomically under the lock.
_LOCK = threading.Lock()
_ACTIVE: List[Callable[[], None]] = []


class _LastInputInfo(ctypes.Structure):
    """Win32 ``LASTINPUTINFO`` — tick of the last input via GetLastInputInfo."""

    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def _default_probe() -> float:
    """Return seconds since last input on Windows; raise elsewhere."""
    if not sys.platform.startswith("win"):
        raise RuntimeError(
            "idle detection has no OS probe on this platform; pass probe=")
    info = _LastInputInfo(ctypes.sizeof(_LastInputInfo), 0)
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        raise RuntimeError("GetLastInputInfo failed")
    millis = (kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
    return max(0.0, millis / 1000.0)


def idle_seconds(*, probe: Optional[IdleProbe] = None) -> float:
    """Return seconds since the last user keyboard / mouse input.

    Pass ``probe`` (a ``() -> float``) to supply the reading in tests; the
    default queries the OS (Windows only). Never negative.
    """
    source = probe if probe is not None else _default_probe
    value = float(source())
    return value if value >= 0.0 else 0.0


def is_idle(threshold_seconds: float, *,
            probe: Optional[IdleProbe] = None) -> bool:
    """Return True if the user has been idle for at least ``threshold_seconds``.

    Raises ``ValueError`` for a negative threshold.
    """
    if threshold_seconds < 0:
        raise ValueError("threshold_seconds must be non-negative")
    return idle_seconds(probe=probe) >= float(threshold_seconds)


def _keepawake_backend() -> str:
    if sys.platform.startswith("win"):
        return "SetThreadExecutionState"
    if sys.platform == "darwin":
        return "caffeinate"
    return "systemd-inhibit"


def plan_keep_awake(*, display: bool = True,
                    system: bool = True) -> Dict[str, Any]:
    """Describe a keep-awake request (pure, no OS call).

    Returns ``{display, system, backend, flags}`` where ``flags`` is the Windows
    ``SetThreadExecutionState`` bitmask the request maps to. Raises
    ``ValueError`` if neither the system nor the display is to be kept awake.
    """
    if not display and not system:
        raise ValueError("keep_awake must keep the system or display awake")
    flags = _ES_CONTINUOUS
    if system:
        flags |= _ES_SYSTEM_REQUIRED
    if display:
        flags |= _ES_DISPLAY_REQUIRED
    return {"display": bool(display), "system": bool(system),
            "backend": _keepawake_backend(), "flags": flags}


def _win_keep_awake(flags: int) -> Callable[[], None]:
    kernel32 = ctypes.windll.kernel32
    kernel32.SetThreadExecutionState(ctypes.c_uint(flags))

    def _release() -> None:
        kernel32.SetThreadExecutionState(ctypes.c_uint(_ES_CONTINUOUS))

    return _release


def _proc_keep_awake(argv: List[str]) -> Callable[[], None]:
    import subprocess  # nosec B404  # reason: fixed argv, no shell
    # fixed argv list, no shell — injection-safe
    proc = subprocess.Popen(argv)  # nosec B603  # nosemgrep

    def _release() -> None:
        proc.terminate()

    return _release


def _caffeinate_argv(plan: Dict[str, Any]) -> List[str]:
    argv = ["caffeinate", "-i"]
    if plan["system"]:
        argv.append("-s")
    if plan["display"]:
        argv.append("-d")
    return argv


def _systemd_argv(plan: Dict[str, Any]) -> List[str]:
    what = "idle:sleep" if plan["display"] else "sleep"
    return ["systemd-inhibit", f"--what={what}",
            "--why=AutoControl unattended run", "sleep", "infinity"]


def _default_driver(plan: Dict[str, Any]) -> Callable[[], None]:
    builders = {
        "SetThreadExecutionState": lambda: _win_keep_awake(plan["flags"]),
        "caffeinate": lambda: _proc_keep_awake(_caffeinate_argv(plan)),
        "systemd-inhibit": lambda: _proc_keep_awake(_systemd_argv(plan)),
    }
    return builders[plan["backend"]]()


@contextmanager
def keep_awake(*, display: bool = True, system: bool = True,
               driver: Optional[KeepAwakeDriver] = None
               ) -> Iterator[Dict[str, Any]]:
    """Scoped context manager keeping the machine (and display) awake.

    Inside the ``with`` block the system will not sleep / screensave; the prior
    state is restored on exit. Pass ``driver`` (``plan -> release_callable``) to
    intercept the OS call in tests. Yields the active plan.
    """
    plan = plan_keep_awake(display=display, system=system)
    acquire = driver if driver is not None else _default_driver
    release = acquire(plan)
    try:
        yield plan
    finally:
        if callable(release):
            release()


def keep_awake_on(*, display: bool = True, system: bool = True,
                  driver: Optional[KeepAwakeDriver] = None) -> Dict[str, Any]:
    """Start keeping the machine awake until :func:`allow_sleep` is called.

    Process-global and lock-guarded; a second call replaces the prior request.
    Pass ``driver`` to intercept the OS call in tests. Returns the active plan.
    """
    plan = plan_keep_awake(display=display, system=system)
    acquire = driver if driver is not None else _default_driver
    release = acquire(plan)
    with _LOCK:
        previous = _ACTIVE[:]
        _ACTIVE.clear()
        _ACTIVE.append(release)
    for old in previous:
        old()
    return plan


def allow_sleep() -> bool:
    """Release a previously-started keep-awake. True if one was active."""
    with _LOCK:
        pending = _ACTIVE[:]
        _ACTIVE.clear()
    for release in pending:
        release()
    return bool(pending)
