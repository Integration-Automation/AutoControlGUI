"""Mobile app lifecycle, alerts and the optional extensions, against the fake backends.

No device is involved: these prove which commands are sent and that a missing
capability is reported instead of imitated.
"""
import pytest

from headless._mobile_doubles import FakeAdbHost, FakeU2, FakeWda
from je_auto_control.android import UIAutomatorDevice
from je_auto_control.ios import IOSDevice
from je_auto_control.utils.device_matrix import run_on_devices
from je_auto_control.wrapper.device_context import (
    AlertNotPresentError, AppState, DeviceCapability, DeviceContext, DeviceError,
    DeviceTimeoutError, DeviceUnsupportedError, open_device,
)
from je_auto_control.wrapper.mobile_extensions import (
    EXTENSION_FEATURES, MobileExtension, accept_alert, app_state, dismiss_alert,
    launch_app, mobile_extension, register_mobile_extension, stop_app, wait_for_app,
)

APP = "com.example.shop"


@pytest.fixture
def adb_host(monkeypatch):
    """A fake ADB host with one attached device, ``phone``, with the app installed."""
    host = FakeAdbHost()
    host.add("phone").installed.add(APP)
    monkeypatch.setattr("je_auto_control.android.adb_client.subprocess.run", host.run)
    monkeypatch.setattr("je_auto_control.android.adb_client.subprocess.Popen", host.popen)
    monkeypatch.setattr("je_auto_control.android.apps._RECORDINGS", {})
    return host


@pytest.fixture
def no_uiautomator(monkeypatch):
    """Pretend uiautomator2 is not installed, whatever the host has."""
    monkeypatch.setattr("je_auto_control.android.input.find_spec", lambda _name: None)
    monkeypatch.setattr("je_auto_control.android.session.find_spec", lambda _name: None)


@pytest.fixture(autouse=True)
def _no_adapters():
    yield
    register_mobile_extension("ios", None)
    register_mobile_extension("android", None)


def _android(**transports):
    return open_device(DeviceContext("android", "phone", adb_path="fake-adb"), **transports)


def _ios(handle):
    return open_device(DeviceContext("ios", "http://wda.test:8100"),
                       device=IOSDevice(url="http://wda.test:8100", handle=handle))


# --- lifecycle ---------------------------------------------------------

def test_launch_wait_stop(adb_host):
    session = _android()
    assert app_state(session, APP) == AppState.NOT_RUNNING
    assert launch_app(session, APP) == "foreground"
    assert wait_for_app(session, APP, timeout_s=1.0) is AppState.FOREGROUND
    app_state_after_stop = stop_app(session, APP)
    assert app_state_after_stop == 'not_running'
    assert adb_host.devices["phone"].input_calls == [
        f"monkey -p {APP} -c android.intent.category.LAUNCHER 1",
        f"am force-stop {APP}",
    ]


def test_ios_launch_wait_stop():
    handle = FakeWda()
    session = _ios(handle)
    assert launch_app(session, APP) is AppState.FOREGROUND
    assert stop_app(session, APP) == "not_running"
    assert [call["op"] for call in handle.input_calls] == ["app_launch", "app_terminate"]


def test_app_that_is_not_installed(adb_host):
    session = _android()
    assert app_state(session, "com.example.absent") is AppState.NOT_INSTALLED
    with pytest.raises(DeviceError, match="not installed"):
        launch_app(session, "com.example.absent")


def test_app_id_cannot_inject_a_shell_command(adb_host):
    session = _android()
    for bad in ("com.example; reboot", "$(reboot)", "", "nopackage"):
        with pytest.raises(DeviceError):
            launch_app(session, bad)
    assert adb_host.devices["phone"].shell_commands == []


def test_wait_for_app_times_out_and_stops_on_cancel(adb_host):
    session = _android()
    with pytest.raises(DeviceTimeoutError, match="not_running"):
        wait_for_app(session, APP, timeout_s=0.05)
    session.cancel()
    with pytest.raises(DeviceError):
        wait_for_app(session, APP, timeout_s=30.0)


def test_unreachable_device_is_not_read_as_not_running(adb_host):
    adb_host.devices["phone"].state = "unauthorized"
    with pytest.raises(DeviceError, match="unauthorized"):
        app_state(_android(), APP)


def test_matrix_stops_the_app_it_started_even_when_the_run_fails(adb_host):
    phone = adb_host.devices["phone"]
    spec = {"platform": "android", "serial": "phone", "adb_path": "fake-adb", "app_id": APP}
    passed = run_on_devices([["AC_android_tap", {"x": 1, "y": 2}]], [dict(spec)])
    assert passed.results[0].success
    assert passed.results[0].app_state == "not_running"
    failed = run_on_devices([["AC_android_key", {"key": "HOME; reboot"}]], [dict(spec)])
    assert failed.results[0].success is False
    assert failed.results[0].app_state == "not_running"
    assert APP not in phone.running
    kept = run_on_devices([], [dict(spec, keep_app=True)])
    assert kept.results[0].app_state == "foreground"


# --- alerts ------------------------------------------------------------

def test_alert_accept_and_dismiss(adb_host):
    wda = FakeWda()
    ios = _ios(wda)
    wda.alert_text = "Allow notifications?"
    assert accept_alert(ios) == "Allow notifications?"
    wda.alert_text = "Rate this app"
    assert dismiss_alert(ios) == "Rate this app"
    assert [call["op"] for call in wda.input_calls] == ["alert.accept", "alert.dismiss"]
    with pytest.raises(AlertNotPresentError):
        accept_alert(ios)

    handle = FakeU2()
    android = _android(ui_device=UIAutomatorDevice(handle=handle))
    handle.buttons = {"android:id/button1", "android:id/button2"}
    assert accept_alert(android) == "android:id/button1"
    assert dismiss_alert(android) == "android:id/button2"
    with pytest.raises(AlertNotPresentError):
        dismiss_alert(android)


def test_android_alert_without_the_widget_tree_says_why(adb_host, no_uiautomator):
    with pytest.raises(DeviceUnsupportedError) as caught:
        accept_alert(_android())
    assert "uiautomator2" in caught.value.reason
    assert caught.value.alternative
    assert adb_host.devices["phone"].input_calls == []


# --- extensions --------------------------------------------------------

def test_clipboard_file_recording_capabilities(adb_host, tmp_path, monkeypatch):
    phone = adb_host.devices["phone"]
    handle = FakeU2()
    session = _android(ui_device=UIAutomatorDevice(handle=handle))
    extension = mobile_extension(session)
    assert isinstance(extension, MobileExtension)
    assert all(extension.capability(name).available for name in EXTENSION_FEATURES)

    apk = tmp_path / "shop.apk"
    apk.write_bytes(b"apk")
    assert extension.install_app(str(apk)) == str(apk.resolve())
    adb_host.host_files[str(apk.resolve())] = b"apk"
    assert extension.push_file(str(apk), "/sdcard/shop.apk") == "/sdcard/shop.apk"
    assert phone.files["/sdcard/shop.apk"] == b"apk"
    pulled = extension.pull_file("/sdcard/shop.apk", str(tmp_path / "out" / "copy.apk"))
    assert adb_host.host_files[pulled] == b"apk"

    extension.set_clipboard("copied 文字")
    assert handle.clipboard == "copied 文字"
    assert extension.get_clipboard() == "copied 文字"

    remote = extension.start_recording(time_limit_s=30)
    assert phone.recording
    assert remote == "/sdcard/autocontrol_recording.mp4"
    with pytest.raises(DeviceError, match="already running"):
        extension.start_recording()
    saved = mobile_extension(session).stop_recording(str(tmp_path / "run.mp4"))
    assert phone.recording is False
    assert adb_host.host_files[saved] == b"mp4-bytes"

    # iOS through WebDriverAgent: the pasteboard, and nothing borrowed from adb.
    def no_adb(*_args, **_kwargs):
        raise AssertionError("adb was invoked for an iOS device")

    monkeypatch.setattr("je_auto_control.android.adb_client.subprocess.run", no_adb)
    monkeypatch.setattr("je_auto_control.android.adb_client.subprocess.Popen", no_adb)
    wda = FakeWda()
    ios_extension = mobile_extension(_ios(wda))
    ios_extension.set_clipboard("hello")
    assert wda.clipboard == "hello"
    for call in (lambda: ios_extension.install_app(str(apk)),
                 lambda: ios_extension.push_file(str(apk), "/tmp/x"),
                 lambda: ios_extension.pull_file("/tmp/x", str(tmp_path / "x")),
                 lambda: ios_extension.start_recording(),
                 lambda: ios_extension.stop_recording(str(tmp_path / "x.mp4")),
                 ios_extension.get_clipboard):
        with pytest.raises(DeviceUnsupportedError) as caught:
            call()
        unsupported_result = caught.value
        assert unsupported_result.reason
        assert unsupported_result.alternative
    assert [call["op"] for call in wda.calls] == ["set_clipboard"]


def test_bad_install_and_paths_are_rejected(adb_host, tmp_path):
    extension = mobile_extension(_android())
    with pytest.raises(DeviceError, match="no such file"):
        extension.install_app(str(tmp_path / "absent.apk"))
    with pytest.raises(DeviceError, match="absolute"):
        extension.pull_file("relative/path", str(tmp_path / "x"))
    with pytest.raises(DeviceError, match="time_limit_s"):
        extension.start_recording(time_limit_s=999)
    assert adb_host.calls == []


def test_adapter_absent_reports_dependency(adb_host, no_uiautomator):
    session = _ios(FakeWda())
    absent_adapter = mobile_extension(session).capability("install")
    assert absent_adapter.state == 'needs_dependency'
    assert "adapter" in absent_adapter.reason
    capabilities = session.capabilities()
    assert capabilities["files"].state == "needs_dependency"
    assert capabilities["recording"].state == "needs_dependency"
    assert capabilities["clipboard"].available
    # Android without uiautomator2: adb covers files, nothing covers the clipboard.
    android = _android().capabilities()
    assert android["files"].available
    assert android["recording"].available
    assert android["clipboard"].state == "needs_dependency"
    assert "uiautomator2" in android["clipboard"].reason
    with pytest.raises(DeviceUnsupportedError):
        mobile_extension(_android()).get_clipboard()


class _HostToolAdapter:
    """A stand-in for a tidevice / pymobiledevice3 adapter: install only."""

    name = "hosttool"

    def __init__(self) -> None:
        self.installed = []

    def capability(self, feature):
        state = "available" if feature == "install" else "unsupported"
        return DeviceCapability(feature, state)

    def install_app(self, source):
        self.installed.append(source)
        return source


def test_registered_adapter_fills_what_wda_lacks():
    adapter = _HostToolAdapter()
    register_mobile_extension("ios", lambda _session: adapter)
    wda = FakeWda()
    session = _ios(wda)
    extension = mobile_extension(session)
    assert extension.install_app("shop.ipa") == "shop.ipa"
    assert adapter.installed == ["shop.ipa"]
    assert session.capabilities()["install"].available
    # What the adapter lacks still comes from WebDriverAgent, or is still missing.
    extension.set_clipboard("x")
    assert wda.clipboard == "x"
    assert extension.capability("files").state == "needs_dependency"
    with pytest.raises(DeviceError):
        register_mobile_extension("windows", None)
