"""System / device defects from the 2026-09-24 audit (fakes only; no real OS state changes).

The file-association content type asked for the quick tip; caffeinate and
systemd-inhibit outlived the process; Windows keep-awake was bound to the
calling thread; empty or non-ASCII input passed or crashed the checksums and
mod-97 produced "00" / "01"; a misspelt framework or "false" evidence gave a
clean compliance report; D-Bus leaked its socket on a failed handshake and
could not send negative ints; window geometry included the invisible borders
and captured minimized windows; pycaw's AudioDevice has no Activate().
"""
import os
import sys
import threading

import pytest

from je_auto_control.utils.checksum.checksum import (
    damm_validate, luhn_validate, mod97_10_check_digits, mod97_10_validate,
    verhoeff_validate,
)
from je_auto_control.utils.compliance.compliance_report import build_compliance_report
from je_auto_control.utils.dbus_client import session_bus
from je_auto_control.utils.file_assoc.file_assoc import _ASSOC_FIELDS
from je_auto_control.utils.idle_keepawake import idle_keepawake


def test_the_content_type_query_is_assocstr_contenttype():
    assert _ASSOC_FIELDS["content_type"] == 14


def test_keep_awake_children_end_with_this_process():
    plan = {"system": True, "display": True}
    assert "-w" in idle_keepawake._caffeinate_argv(plan)
    assert str(os.getpid()) in idle_keepawake._caffeinate_argv(plan)
    argv = idle_keepawake._systemd_argv(plan)
    assert "infinity" not in argv and f"--pid={os.getpid()}" in argv


def test_windows_keep_awake_is_held_by_its_own_thread(monkeypatch):
    threads = []

    class Kernel32:
        def SetThreadExecutionState(self, flags):  # noqa: N802 - Win32 name
            threads.append((threading.get_ident(), int(flags)))
            return 0

    monkeypatch.setattr(idle_keepawake, "ctypes", type("C", (), {
        "windll": type("W", (), {"kernel32": Kernel32()}),
        "c_uint": staticmethod(lambda v: v)}))
    release = idle_keepawake._win_keep_awake(0x80000003)
    release()
    holders = {ident for ident, _flags in threads}
    assert len(holders) == 1 and threading.get_ident() not in holders
    assert threads[0][1] == 0x80000003 and threads[-1][1] == 0x80000000


@pytest.mark.parametrize("check", [verhoeff_validate, damm_validate])
@pytest.mark.parametrize("value", ["", "abc", "--"])
def test_no_digits_is_not_a_valid_number(check, value):
    assert check(value) is False


def test_non_ascii_digits_are_ignored_not_crashed_on():
    assert luhn_validate("4" + chr(0xB2)) is False


def test_mod97_check_digits_follow_iso_7064():
    for value in range(2000):
        digits = mod97_10_check_digits(str(value))
        assert 2 <= int(digits) <= 98
        assert mod97_10_validate(f"{value}{digits}")


def test_compliance_rejects_unknown_frameworks_and_false_strings():
    report = build_compliance_report({"secrets_scanned": "false"}, frameworks=["SOC 2"])
    assert report["summary"]["total"] > 0
    statuses = {c["evidence_key"]: c["status"] for c in report["controls"]}
    assert statuses.get("secrets_scanned", "gap") == "gap"
    with pytest.raises(ValueError, match="unknown compliance framework"):
        build_compliance_report({}, frameworks=["SOX"])


def test_dbus_integers_get_a_type_that_fits():
    assert session_bus._int_signature(5) == "u"
    assert session_bus._int_signature(-1) == "i"
    assert session_bus._int_signature(2 ** 40) == "x"
    with pytest.raises(session_bus.DBusError):
        session_bus._int_signature(2 ** 70)


def test_a_failed_dbus_handshake_closes_the_socket(monkeypatch):
    bus = session_bus.SessionBus.__new__(session_bus.SessionBus)
    closed = []
    monkeypatch.setattr(bus, "close", lambda: closed.append(True), raising=False)

    def refuse():
        raise session_bus.DBusError("auth refused")

    monkeypatch.setattr(bus, "_authenticate", refuse, raising=False)
    bus.address = "unix:path=/tmp/x"
    monkeypatch.setattr(session_bus, "_socket_target", lambda _a: ("/tmp/x", False))

    class _Sock:
        def connect(self, _target):
            return None

    monkeypatch.setattr(session_bus.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(session_bus.socket, "socket", lambda *_a: _Sock())
    with pytest.raises(session_bus.DBusError):
        bus.connect()
    assert closed


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 window geometry")
def test_window_geometry_skips_minimized_and_uses_the_frame_bounds(monkeypatch):
    import ctypes
    from je_auto_control.utils.window_capture import window_capture

    class User32:
        def __init__(self, iconic):
            self.iconic = iconic

        def IsIconic(self, _hwnd):  # noqa: N802
            return self.iconic

        def GetWindowRect(self, _hwnd, _rect):  # noqa: N802
            raise AssertionError("the DWM frame bounds should have been used")

    class Dwm:
        def DwmGetWindowAttribute(self, _hwnd, attribute, rect, _size):  # noqa: N802
            assert attribute == 9
            target = rect._obj
            target.left, target.top, target.right, target.bottom = 10, 20, 110, 220
            return 0

    windll = type("W", (), {})()
    windll.user32, windll.dwmapi = User32(True), Dwm()
    monkeypatch.setattr(ctypes, "windll", windll)
    assert window_capture._win32_geometry(1) is None
    windll.user32 = User32(False)
    assert window_capture._win32_geometry(1) == (10, 20, 100, 200)


def test_new_pycaw_audio_devices_are_supported(monkeypatch):
    pytest.importorskip("comtypes")
    pycaw = pytest.importorskip("pycaw.pycaw")
    from je_auto_control.utils.system_volume import system_volume

    class Device:
        EndpointVolume = object()

    monkeypatch.setattr(pycaw.AudioUtilities, "GetSpeakers", staticmethod(lambda: Device()))
    driver = system_volume._PycawDriver()
    assert driver._volume is Device.EndpointVolume
