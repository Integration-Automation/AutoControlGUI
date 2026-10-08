"""Shared pieces of the GUI benchmarks: environment, memory, percentiles, before/after comparison.

Nothing here imports Qt at module level, and nothing shows a window: the
benchmarks run on the ``offscreen`` platform plugin unless ``QT_QPA_PLATFORM``
says otherwise, and never read or write the user's GUI settings.
"""
import json
import os
import platform
import statistics
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence

SETTINGS_ENV = "JE_AUTOCONTROL_GUI_SETTINGS"
# What has to match for two reports to be comparable.
COMPARABLE_KEYS = ("benchmark", "workload")
COMPARABLE_ENVIRONMENT = ("platform", "machine", "python", "pyside6", "qt_platform", "screens")


def prepare_process() -> None:
    """Keep this process off the desktop and out of the user's settings."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ[SETTINGS_ENV] = "off"


def rss_mb() -> Optional[float]:
    """Resident memory of this process in MiB, or ``None`` when it cannot be read."""
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1048576, 1)
    except ImportError:
        pass
    if sys.platform == "win32":
        return _windows_rss_mb()
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1048576 if sys.platform == "darwin" else 1024), 1)


def _windows_rss_mb() -> Optional[float]:
    import ctypes
    from ctypes import wintypes

    class _Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    counters = _Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
    if not kernel32.K32GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return None
    return round(counters.WorkingSetSize / 1048576, 1)


def wait_for_workers(app: Any, timeout: float = 60.0) -> None:
    """Pump events until the GUI's worker threads are done, or ``timeout`` seconds pass.

    A tab opened in a shown window starts its first refresh on a worker
    thread. Leaving the process with ``os._exit`` while one runs is an access
    violation inside ``ExitProcess`` on Windows.
    """
    import threading
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and any(t.name.startswith("gui-worker") for t in threading.enumerate()):
        app.processEvents()
        time.sleep(0.02)


def environment(app: Any = None) -> Dict[str, Any]:
    """Describe the machine and the Qt it ran on; ``app`` adds what only a live application knows."""
    info: Dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "qt_platform": os.environ.get("QT_QPA_PLATFORM", ""),
    }
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        info["pyside6"], info["qt"] = PySide6.__version__, qVersion()
    except ImportError:
        info["pyside6"] = info["qt"] = None
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            info["je_auto_control"] = version("je_auto_control")
        except PackageNotFoundError:
            info["je_auto_control"] = None
    except ImportError:
        info["je_auto_control"] = None
    if app is not None:
        info["qt_platform"] = app.platformName()
        info["screens"] = [[screen.geometry().width(), screen.geometry().height(), screen.devicePixelRatio()]
                           for screen in app.screens()]
    return info


def percentile(samples: Sequence[float], percent: float) -> float:
    """The ``percent``-th percentile by nearest rank; 0.0 for no samples."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = max(1, -(-len(ordered) * percent // 100))
    return float(ordered[int(min(rank, len(ordered))) - 1])


def summary(samples: Iterable[float]) -> Dict[str, Any]:
    """Median, extremes and the samples themselves, rounded to a tenth of a millisecond."""
    values = [round(float(value), 1) for value in samples]
    if not values:
        return {"median": None, "min": None, "max": None, "samples": []}
    return {"median": round(statistics.median(values), 1), "min": min(values), "max": max(values),
            "samples": values}


def _numbers(report: Dict[str, Any], prefix: str = "") -> Dict[str, float]:
    found: Dict[str, float] = {}
    for key, value in report.items():
        name = f"{prefix}{key}"
        if key in ("environment", "samples"):
            continue
        if isinstance(value, dict):
            found.update(_numbers(value, f"{name}."))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            found[name] = float(value)
    return found


def compare(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Set two reports of the same workload on the same environment side by side.

    Reports that differ in benchmark, workload or environment are not
    compared: the result says which keys differ and carries no numbers.
    """
    differing: List[str] = [key for key in COMPARABLE_KEYS if before.get(key) != after.get(key)]
    env_before, env_after = before.get("environment", {}), after.get("environment", {})
    differing += [f"environment.{key}" for key in COMPARABLE_ENVIRONMENT if env_before.get(key) != env_after.get(key)]
    if differing:
        return {"comparable": False, "differs_in": differing, "changes": {}}
    old, new = _numbers(before), _numbers(after)
    changes = {}
    for name in sorted(set(old) & set(new)):
        delta = round(new[name] - old[name], 1)
        percent = round(delta / old[name] * 100, 1) if old[name] else None
        changes[name] = {"before": old[name], "after": new[name], "delta": delta, "percent": percent}
    return {"comparable": True, "differs_in": [], "changes": changes}


def load(path: str) -> Dict[str, Any]:
    """Read a report written by :func:`emit`."""
    with open(path, encoding="utf-8") as handle:
        loaded: Dict[str, Any] = json.load(handle)
    return loaded


def emit(report: Dict[str, Any], output: Optional[str] = None) -> None:
    """Write ``report`` as JSON to ``output``, or to stdout."""
    text = json.dumps(report, indent=2, sort_keys=True)
    if output:
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        return
    sys.stdout.write(text + "\n")
    sys.stdout.flush()
