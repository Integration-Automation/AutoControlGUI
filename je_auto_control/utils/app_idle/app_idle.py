"""Wait until an application stops being busy before driving the next step.

A click fired while the app is still churning — the busy / wait cursor is up, a
dialog is mid-paint, a long handler is running — is dropped or mis-targeted.
``smart_waits`` watches *pixels* settling; this watches the app's *busy signal*
settle instead, which is cheaper and survives animated-but-idle UI. It reuses
:class:`settle_detector.SettleTracker`: each poll feeds ``1.0`` when busy and
``0.0`` when idle, and the wait returns once the app has read idle for
``quiet_samples`` polls in a row (a fresh busy spike resets the run).

* :func:`wait_until_app_idle` — poll a ``busy_probe`` until the app settles idle
  or a timeout, with injectable ``clock`` / ``sleep`` / ``busy_probe``.
* :func:`idle_point` — pure: the index in a recorded busy/idle sample series at
  which it first becomes settled-idle.

The default probe reports the Windows busy / app-starting cursor; every wait and
settle decision runs through the injectable seam, so it is fully testable
without an app. Imports no ``PySide6``.
"""
import sys
import time
from typing import Any, Callable, Dict, Optional, Sequence

from je_auto_control.utils.settle_detector import SettleTracker, settle_point

# A busy probe returns truthy while the application is busy.
BusyProbe = Callable[[], bool]

# Windows busy cursors (IDC_WAIT / IDC_APPSTARTING).
_IDC_WAIT = 32514
_IDC_APPSTARTING = 32650


def idle_point(busy_samples: Sequence[Any], *,
               quiet_samples: int = 3) -> Optional[int]:
    """Index at which a busy/idle sample series first settles idle (pure).

    Each truthy sample is "busy"; the series settles once it has read idle for
    ``quiet_samples`` in a row. Returns ``None`` if it never settles.
    """
    churns = [1.0 if bool(sample) else 0.0 for sample in busy_samples]
    return settle_point(churns, quiet_samples=int(quiet_samples), max_churn=0.0)


def wait_until_app_idle(*, busy_probe: Optional[BusyProbe] = None,
                        quiet_samples: int = 3, timeout_s: float = 10.0,
                        interval_s: float = 0.1,
                        clock: Callable[[], float] = time.monotonic,
                        sleep: Callable[[float], None] = time.sleep
                        ) -> Dict[str, Any]:
    """Block until the app reads idle for ``quiet_samples`` polls, or timeout.

    Returns ``{idle, polls, quiet_run, elapsed_s}``. ``clock`` / ``sleep`` /
    ``busy_probe`` are injectable for deterministic tests; the default probe
    reports the Windows busy cursor.
    """
    probe = busy_probe if busy_probe is not None else _default_busy_probe
    tracker = SettleTracker(quiet_samples=int(quiet_samples), max_churn=0.0)
    start = clock()
    deadline = start + float(timeout_s)
    polls = 0
    quiet_run = 0
    while True:
        polls += 1
        state = tracker.update(1.0 if bool(probe()) else 0.0)
        quiet_run = state.quiet_run
        if state.settled:
            return {"idle": True, "polls": polls, "quiet_run": quiet_run,
                    "elapsed_s": round(clock() - start, 4)}
        if clock() >= deadline:
            return {"idle": False, "polls": polls, "quiet_run": quiet_run,
                    "elapsed_s": round(clock() - start, 4)}
        sleep(float(interval_s))


def _cursor_is_busy() -> bool:
    """Return True when the Windows global cursor is a busy / app-starting one."""
    import ctypes

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class _CURSORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("flags", ctypes.c_uint),
                    ("hCursor", ctypes.c_void_p), ("ptScreenPos", _POINT)]

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]  # reason: win32-only ctypes
    info = _CURSORINFO()
    info.cbSize = ctypes.sizeof(_CURSORINFO)
    if not user32.GetCursorInfo(ctypes.byref(info)):
        return False
    busy = {user32.LoadCursorW(None, _IDC_WAIT),
            user32.LoadCursorW(None, _IDC_APPSTARTING)}
    return info.hCursor in busy


def _default_busy_probe() -> bool:
    """Default busy probe: the Windows busy cursor; raise on other platforms."""
    if not sys.platform.startswith("win"):
        raise RuntimeError(
            "app-idle has no OS busy probe on this platform; pass busy_probe=")
    return _cursor_is_busy()
