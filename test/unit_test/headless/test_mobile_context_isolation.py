"""Device contexts: two devices in one process never reach each other.

Driven against the fake ADB host and fake WebDriverAgent client in
``_mobile_doubles`` — no device is involved, so these prove the routing and
the session state machine, not that a phone accepts the commands.
"""
import threading

import pytest

from headless._mobile_doubles import FakeAdbHost, FakeWda
from je_auto_control.android import AdbError, client as android_client
from je_auto_control.ios import IOSDevice, client as ios_client
from je_auto_control.utils.device_matrix import run_on_devices
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper.device_context import (
    DeviceCancelledError, DeviceClosedError, DeviceContext, DeviceError,
    DevicePermissionError, DeviceTimeoutError, DeviceUnavailableError,
    bound_session, open_device, use_device,
)


@pytest.fixture
def adb_host(monkeypatch):
    """A fake ADB host with two attached devices, ``left`` and ``right``."""
    host = FakeAdbHost()
    host.add("left")
    host.add("right")
    monkeypatch.setattr("je_auto_control.android.adb_client.subprocess.run", host.run)
    monkeypatch.setattr("je_auto_control.android.adb_client.shutil.which",
                        lambda _name: "fake-adb")
    from je_auto_control.utils.executor import action_executor
    monkeypatch.setattr(action_executor, "_android_client_cache", {})
    return host


def _android(serial: str, **kwargs) -> DeviceContext:
    return DeviceContext("android", serial, adb_path="fake-adb", **kwargs)


def test_parallel_devices_do_not_change_default(adb_host):
    android_client.reset_default_ui_device()
    ios_client.reset_default_ios_device()
    from je_auto_control.utils.executor import action_executor
    # No serial in the action: each worker must reach its own device anyway.
    report = run_on_devices(
        [["AC_android_tap", {"x": 11, "y": 22}]],
        [{"platform": "android", "serial": "left", "adb_path": "fake-adb"},
         {"platform": "android", "serial": "right", "adb_path": "fake-adb"}],
        max_parallel=2,
    )
    assert report.passed == 2, report.to_dict()
    left_calls = adb_host.devices["left"]
    assert left_calls.device_id == "left"
    assert adb_host.calls_for("left") == [["shell", "input tap 11 22"]]
    assert adb_host.calls_for("right") == [["shell", "input tap 11 22"]]
    # Nothing went to "whichever device adb picks", and no default was created.
    assert adb_host.calls_for(None) == []
    assert android_client._DEFAULT_DEVICE is None
    assert ios_client._DEFAULT_DEVICE is None
    assert action_executor._android_client_cache == {}
    assert bound_session("android") is None


def test_explicit_serial_beats_the_bound_device(adb_host):
    from je_auto_control.utils.executor.action_executor import executor
    with open_device(_android("left")) as left, use_device(left):
        executor.event_dict["AC_android_tap"](1, 2, serial="right", adb_path="fake-adb")
        executor.event_dict["AC_android_tap"](3, 4)
    assert adb_host.calls_for("right") == [["shell", "input tap 1 2"]]
    assert adb_host.calls_for("left") == [["shell", "input tap 3 4"]]


def test_session_cancel_only_target(adb_host):
    left_session = open_device(_android("left"))
    right_session = open_device(_android("right"))
    left_session.cancel()
    assert left_session.connected is False
    assert right_session.connected is True
    with pytest.raises(DeviceCancelledError):
        left_session.invoke("tap", lambda: left_session.adb.tap(1, 1))
    right_session.invoke("tap", lambda: right_session.adb.tap(5, 6))
    assert adb_host.devices["left"].input_calls == []
    assert adb_host.devices["right"].input_calls == ["input tap 5 6"]


def test_cancel_releases_a_caller_waiting_on_the_device(adb_host):
    gate = threading.Event()
    adb_host.devices["left"].gate = gate
    session = open_device(_android("left"))
    raised = []

    def blocked() -> None:
        try:
            session.invoke("tap", lambda: session.adb.tap(1, 1))
        except DeviceError as error:
            raised.append(error)

    worker = threading.Thread(target=blocked)
    worker.start()
    session.cancel()
    worker.join(2)
    gate.set()
    assert not worker.is_alive()
    assert isinstance(raised[0], DeviceCancelledError)


def test_timeout_closes_the_session(adb_host):
    gate = threading.Event()
    adb_host.devices["left"].gate = gate
    session = open_device(_android("left", timeout_s=0.1))
    with pytest.raises(DeviceTimeoutError):
        session.invoke("tap", lambda: session.adb.tap(1, 1))
    gate.set()
    # The tap's outcome is unknown, so the next step must not be sent on top.
    assert session.connected is False
    with pytest.raises(DeviceClosedError):
        session.invoke("tap", lambda: session.adb.tap(2, 2))


def test_device_capability_probe_has_no_input(adb_host):
    session = open_device(_android("left"))
    capabilities = session.capabilities()
    probe_input_calls = adb_host.devices["left"].input_calls
    assert probe_input_calls == []
    assert capabilities["input"].state == "available"
    assert capabilities["screenshot"].available
    assert capabilities["ui_tree"].state == "needs_dependency"
    assert "uiautomator2" in capabilities["ui_tree"].reason


def test_ios_capability_probe_has_no_input():
    handle = FakeWda()
    session = open_device(DeviceContext("ios", "http://wda.test:8100"),
                          device=IOSDevice(handle=handle))
    capabilities = session.capabilities()
    assert handle.input_calls == []
    assert capabilities["input"].state == "available"


def test_unauthorized_device_needs_permission(adb_host):
    adb_host.add("locked", state="unauthorized")
    session = open_device(_android("locked"))
    capability = session.capabilities()["input"]
    assert capability.state == "needs_permission"
    assert "USB debugging" in capability.reason
    with pytest.raises(DevicePermissionError) as caught:
        session.adb.tap(1, 1)
    # Still the type existing callers catch.
    assert isinstance(caught.value, AdbError)
    assert adb_host.devices["locked"].input_calls == []


def test_missing_device_and_missing_adb_are_reported(adb_host, monkeypatch):
    gone = open_device(_android("gone")).capabilities()["input"]
    assert gone.state == "needs_dependency"
    assert "gone" in gone.reason
    monkeypatch.setattr("je_auto_control.android.adb_client.shutil.which", lambda _name: None)
    no_adb = open_device(DeviceContext("android", "left")).capabilities()["input"]
    assert no_adb.state == "needs_dependency"
    assert "platform-tools" in no_adb.reason


def test_adb_timeout_is_a_framework_timeout(monkeypatch):
    import subprocess

    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))  # nosemgrep

    monkeypatch.setattr("je_auto_control.android.adb_client.subprocess.run", slow)
    session = open_device(_android("left"))
    with pytest.raises(DeviceTimeoutError) as caught:
        session.adb.tap(1, 1)
    assert isinstance(caught.value, AdbError)
    assert isinstance(caught.value, AutoControlException)


def test_every_backend_error_is_a_device_error():
    from je_auto_control.android import AdbNotAvailable, UIAutomatorUnavailableError
    from je_auto_control.ios import IOSUnavailableError
    for error in (AdbNotAvailable, UIAutomatorUnavailableError, IOSUnavailableError):
        assert issubclass(error, DeviceUnavailableError)
        assert issubclass(error, RuntimeError)
    assert issubclass(AdbError, DeviceError)


def test_session_owns_only_the_transport_it_built():
    handle = FakeWda()
    device = IOSDevice(handle=handle)
    session = open_device(DeviceContext("ios", "http://wda.test:8100"), device=device)
    session.close()
    session.close()
    assert session.connected is False
    # A transport the caller handed in is the caller's to keep using.
    assert device.handle is handle


def test_context_is_frozen_and_validated():
    context = DeviceContext("ios", "http://wda.test:8100")
    with pytest.raises(AttributeError):
        context.device_id = "other"
    with pytest.raises(DeviceError):
        DeviceContext("windows", "x")
    with pytest.raises(DeviceError):
        DeviceContext("android", "x", timeout_s=0)
    assert DeviceContext.from_spec({"platform": "desktop"}) is None
    spec = DeviceContext.from_spec({"platform": "ios", "url": "http://a:8100"})
    assert spec == DeviceContext("ios", "http://a:8100")
