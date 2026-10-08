"""Mobile device matrix — run one action script across many devices.

Single-device Android (adb / uiautomator2) and iOS (WebDriverAgent) control
already exists. This module fans a single action list out across a list of
devices *in parallel*, giving each device its own isolated executor (so the
runtime variable scopes never collide between threads) and aggregating the
per-device pass/fail outcome.

Each mobile device also gets its own :class:`DeviceSession`, opened from an
explicit :class:`DeviceContext` and bound for the duration of that device's
run. An ``AC_android_*`` / ``AC_ios_*`` step that names no ``serial`` / ``url``
therefore reaches the device its worker is running, never a process-wide
default another worker could have set.

The action list addresses the current device through a bound variable, e.g.
``${device.serial}`` / ``${device.url}``, so the same script targets every
device::

    run_on_devices(
        actions=[["AC_android_tap", {"x": 100, "y": 200,
                                      "serial": "${device.serial}"}]],
        devices=[{"platform": "android", "serial": "emulator-5554"},
                 {"platform": "android", "serial": "emulator-5556"}],
    )
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper.device_context import DeviceContext, open_device, use_device


@dataclass
class DeviceResult:
    """Outcome of running the script against one device."""

    device_id: str
    platform: str
    success: bool
    duration_s: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MatrixReport:
    """Aggregated per-device outcomes."""

    results: List[DeviceResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.total > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "success": self.success,
            "results": [r.to_dict() for r in self.results],
        }


def _device_id(device: Dict[str, Any], index: int) -> str:
    return str(device.get("serial") or device.get("url") or f"device-{index}")


def _run_one_device(actions: List[Any], device: Dict[str, Any],
                    index: int, var_name: str) -> DeviceResult:
    """Run ``actions`` against a single device on a fresh executor."""
    from je_auto_control.utils.executor.action_executor import Executor
    runner = Executor()
    runner.variables.set(var_name, device)
    device_id = _device_id(device, index)
    platform = str(device.get("platform", ""))
    started = time.monotonic()
    try:
        context = DeviceContext.from_spec(device)
        if context is None:
            # Not a mobile spec: nothing to bind, the list runs as written.
            runner.execute_action(actions, raise_on_error=True)
        else:
            with open_device(context) as session, use_device(session):
                runner.execute_action(actions, raise_on_error=True)
        return DeviceResult(device_id, platform, True,
                            time.monotonic() - started)
    # The executor's own containment set: an ImageNotFoundException or a
    # KeyError on one device used to abort the whole matrix.
    except (AutoControlException, OSError, RuntimeError, ArithmeticError,
            AttributeError, TypeError, ValueError, LookupError) as error:
        return DeviceResult(device_id, platform, False,
                            time.monotonic() - started, repr(error))


def run_on_devices(actions: List[Any],
                   devices: List[Dict[str, Any]],
                   max_parallel: int = 4,
                   var_name: str = "device") -> MatrixReport:
    """Run ``actions`` against every device in parallel; aggregate results.

    :param actions: an AC_* action list (may reference ``${device.*}``).
    :param devices: list of device specs (``platform`` + ``serial`` / ``url``).
    :param max_parallel: maximum concurrent device runs.
    :param var_name: variable each device spec is bound to during the run.
    """
    if not isinstance(devices, list) or not devices:
        raise ValueError("devices must be a non-empty list of device specs")
    if not isinstance(actions, list):
        raise ValueError("actions must be a list")
    bad = [index for index, device in enumerate(devices) if not isinstance(device, dict)]
    if bad:
        # Checked before any device runs: one string spec raised AttributeError
        # after earlier devices had run, and their results were lost.
        raise ValueError(f"device specs must be objects; not at index {bad}")
    workers = max(1, min(int(max_parallel), len(devices)))
    report = MatrixReport()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_run_one_device, actions, device, index, var_name)
            for index, device in enumerate(devices)
        ]
        report.results = [future.result() for future in futures]
    return report
