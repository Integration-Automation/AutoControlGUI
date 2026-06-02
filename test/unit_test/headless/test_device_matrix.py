"""Headless tests for the mobile device matrix."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.device_matrix import MatrixReport, run_on_devices

# A device-agnostic action list: bind a var and assert nothing touches HW.
# Uses ${device.platform} which every device spec carries.
_ACTIONS = [["AC_set_var", {"name": "id", "value": "${device.platform}"}]]


def test_facade_export():
    assert hasattr(ac, "run_on_devices")


def test_runs_each_device():
    devices = [
        {"platform": "android", "serial": "a"},
        {"platform": "android", "serial": "b"},
        {"platform": "ios", "url": "http://localhost:8100"},
    ]
    report = run_on_devices(_ACTIONS, devices, max_parallel=2)
    assert isinstance(report, MatrixReport)
    assert report.total == 3
    assert report.passed == 3
    assert report.success is True
    ids = {r.device_id for r in report.results}
    assert ids == {"a", "b", "http://localhost:8100"}


def test_failure_isolated_per_device():
    # An action that raises (unknown command) fails only its own device.
    devices = [{"platform": "android", "serial": "a"}]
    report = run_on_devices(
        [["AC_assert_window", {"title": "zzz_none", "exists": True}]],
        devices,
    )
    assert report.total == 1
    assert report.passed == 0
    assert report.results[0].error is not None


def test_empty_devices_raises():
    with pytest.raises(ValueError):
        run_on_devices(_ACTIONS, [])


def test_executor_command():
    from je_auto_control.utils.executor.action_executor import executor
    out = executor.event_dict["AC_run_device_matrix"](
        _ACTIONS, [{"platform": "android", "serial": "x"}],
    )
    assert out["total"] == 1
    assert out["passed"] == 1
