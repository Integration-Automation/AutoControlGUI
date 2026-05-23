"""Phase 9.7: Android ADB backend tests (no real device required).

Every test patches ``subprocess.run`` so the suite passes on a CI
runner with no adb binary, no phone attached, and no platform-tools
package. We verify the constructed argv, parse the device list, and
exercise the executor's AC_android_* dispatch entries.
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from je_auto_control.android import (
    AdbClient, AdbError, AdbNotAvailable, AndroidDevice,
)


# --- module-level fixtures -------------------------------------------

@pytest.fixture
def stub_adb_path(monkeypatch, tmp_path):
    """Pretend an ``adb`` binary exists at ``tmp_path / "adb"``."""
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("#!/usr/bin/env true")
    monkeypatch.setattr(
        "je_auto_control.android.adb_client.shutil.which",
        lambda name: str(fake_adb) if name == "adb" else None,
    )
    yield str(fake_adb)


@pytest.fixture(autouse=True)
def _reset_android_client_cache():
    """Each test starts with a fresh AC_android_* client cache."""
    from je_auto_control.utils.executor import action_executor as exec_mod
    exec_mod._android_client_cache.clear()
    yield
    exec_mod._android_client_cache.clear()


# --- constructor -----------------------------------------------------

def test_constructor_raises_when_adb_missing(monkeypatch):
    monkeypatch.setattr(
        "je_auto_control.android.adb_client.shutil.which",
        lambda name: None,
    )
    with pytest.raises(AdbNotAvailable):
        AdbClient()


def test_explicit_adb_path_overrides_path_lookup(stub_adb_path):
    client = AdbClient(adb_path=stub_adb_path)
    assert client.adb_path == stub_adb_path


# --- run() argv construction ----------------------------------------

def _patched_run(returncode: int = 0, stdout: bytes = b"",
                 stderr: bytes = b""):
    completed = subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )
    return patch(
        "je_auto_control.android.adb_client.subprocess.run",
        return_value=completed,
    )


def test_run_uses_default_serial_when_set(stub_adb_path):
    client = AdbClient(adb_path=stub_adb_path, default_serial="emulator-5554")
    with _patched_run(stdout=b"ok") as run:
        client.run(["shell", "echo"])
    cmd = run.call_args[0][0]
    assert cmd[0] == stub_adb_path
    assert cmd[1:3] == ["-s", "emulator-5554"]
    assert cmd[3:] == ["shell", "echo"]


def test_run_explicit_serial_overrides_default(stub_adb_path):
    client = AdbClient(adb_path=stub_adb_path, default_serial="abc")
    with _patched_run() as run:
        client.run(["shell", "echo"], serial="xyz")
    cmd = run.call_args[0][0]
    assert cmd[1:3] == ["-s", "xyz"]


def test_run_raises_on_nonzero_exit(stub_adb_path):
    client = AdbClient(adb_path=stub_adb_path)
    with _patched_run(returncode=1, stderr=b"no device"):
        with pytest.raises(AdbError, match="no device"):
            client.run(["shell", "echo"])


def test_run_subprocess_error_wrapped(stub_adb_path):
    client = AdbClient(adb_path=stub_adb_path)
    with patch(
        "je_auto_control.android.adb_client.subprocess.run",
        side_effect=OSError("file not found"),
    ):
        with pytest.raises(AdbError, match="file not found"):
            client.run(["devices"])


# --- shell() / tap / swipe / key / text -----------------------------

def test_shell_returns_decoded_stdout(stub_adb_path):
    client = AdbClient(adb_path=stub_adb_path)
    with _patched_run(stdout=b"hello\n"):
        out = client.shell("echo hello")
    assert out == "hello\n"


@pytest.mark.parametrize("method,args,expected_cmd", [
    ("tap", (100, 200), "input tap 100 200"),
    ("swipe", (10, 20, 30, 40),
     "input swipe 10 20 30 40 250"),  # default duration
    ("key_event", ("KEYCODE_HOME",), "input keyevent HOME"),
    ("key_event", ("BACK",), "input keyevent BACK"),
    ("text", ("hello world",), 'input text "hello%sworld"'),
])
def test_input_dispatch_builds_correct_shell_command(
    stub_adb_path, method, args, expected_cmd,
):
    client = AdbClient(adb_path=stub_adb_path)
    with _patched_run() as run:
        getattr(client, method)(*args)
    cmd = run.call_args[0][0]
    assert cmd[-2:] == ["shell", expected_cmd]


def test_text_rejects_non_string(stub_adb_path):
    client = AdbClient(adb_path=stub_adb_path)
    with pytest.raises(AdbError, match="string"):
        client.text(12345)  # type: ignore[arg-type]  # NOSONAR python:S5655  # reason: intentional bad-type negative test


# --- list_devices ---------------------------------------------------

_DEVICES_LIST_OUTPUT = (
    b"List of devices attached\n"
    b"emulator-5554  device product:sdk_phone_x86 model:Pixel_5 "
    b"transport_id:42\n"
    b"abc123def      unauthorized\n"
    b"\n"
).replace(b"  ", b" ")


def test_list_devices_parses_adb_devices_output(stub_adb_path):
    client = AdbClient(adb_path=stub_adb_path)
    with _patched_run(stdout=_DEVICES_LIST_OUTPUT):
        devices = client.list_devices()
    assert len(devices) == 2
    primary = devices[0]
    assert primary.serial == "emulator-5554"
    assert primary.state == "device"
    assert primary.model == "Pixel_5"
    assert primary.transport_id == "42"
    assert primary.is_ready() is True

    pending = devices[1]
    assert pending.serial == "abc123def"
    assert pending.is_ready() is False


# --- screenshot ----------------------------------------------------

def test_screencap_returns_raw_png_bytes(stub_adb_path):
    client = AdbClient(adb_path=stub_adb_path)
    with _patched_run(stdout=b"\x89PNG\r\n\x1a\nfake-screen-bytes"):
        png = client.screencap_png()
    assert png.startswith(b"\x89PNG")


def test_save_screenshot_writes_to_disk(stub_adb_path, tmp_path):
    client = AdbClient(adb_path=stub_adb_path)
    target = tmp_path / "out" / "phone.png"
    with _patched_run(stdout=b"\x89PNG\r\n\x1a\nbytes"):
        result = client.save_screenshot(str(target))
    assert result.exists()
    assert result.read_bytes().startswith(b"\x89PNG")


# --- AC_android_* dispatch -----------------------------------------

def test_executor_registers_every_android_command():
    from je_auto_control.utils.executor.action_executor import executor
    for name in (
        "AC_android_tap", "AC_android_swipe", "AC_android_key",
        "AC_android_text", "AC_android_screenshot",
        "AC_android_list_devices", "AC_android_shell",
    ):
        assert name in executor.event_dict, f"executor missing {name}"


def test_ac_android_tap_forwards_to_client(stub_adb_path):
    from je_auto_control.utils.executor.action_executor import executor
    fn = executor.event_dict["AC_android_tap"]
    with _patched_run() as run:
        fn(x=42, y=84, adb_path=stub_adb_path)
    cmd = run.call_args[0][0]
    assert "input tap 42 84" in " ".join(cmd)


def test_ac_android_list_devices_returns_dict_payload(stub_adb_path):
    from je_auto_control.utils.executor.action_executor import executor
    fn = executor.event_dict["AC_android_list_devices"]
    with _patched_run(stdout=_DEVICES_LIST_OUTPUT):
        payload = fn(adb_path=stub_adb_path)
    assert isinstance(payload, list)
    assert payload[0]["serial"] == "emulator-5554"
    assert payload[0]["state"] == "device"


def test_ac_android_screenshot_returns_path(stub_adb_path, tmp_path):
    from je_auto_control.utils.executor.action_executor import executor
    fn = executor.event_dict["AC_android_screenshot"]
    target = tmp_path / "phone.png"
    with _patched_run(stdout=b"\x89PNG"):
        result = fn(file_path=str(target), adb_path=stub_adb_path)
    assert result == str(target)
    assert target.exists()


def test_android_device_dataclass_is_ready():
    assert AndroidDevice(serial="x", state="device").is_ready() is True
    assert AndroidDevice(serial="x", state="offline").is_ready() is False
