"""Windows and macOS capabilities are judged from facts, not assumed.

Every desktop here is described through fake facts, so the judgement is tested
on any runner. One test reads the live Windows session: those queries are
read-only (a token query, a session id, a desktop name, a 1x1 screen copy) and
send no input, change no focus and show no window.
"""
import sys

import pytest

import je_auto_control as ac
from je_auto_control.wrapper import capability_probes as probes
from je_auto_control.wrapper.capabilities import (
    BackendContext, CapabilityStatus, probe_capabilities,
)
from je_auto_control.wrapper.capability_probes import MacFacts, WindowsFacts

_GOOD = dict(integrity="medium", session_id=1, input_desktop="Default",
             hook_access=True, capture_ok=True)


def _windows(**changes):
    facts = WindowsFacts(**{**_GOOD, **changes})
    return probe_capabilities(BackendContext(
        platform="win32", windows_facts=lambda: facts,
        backend_version=lambda backend: f"{backend}-test 1.2"))


def _mac(**facts):
    return probe_capabilities(BackendContext(
        platform="darwin", mac_facts=lambda: MacFacts(**facts),
        backend_version=lambda backend: f"{backend}-test 3.4"))


def _states(snapshot):
    return {item.name: item.state.value for item in snapshot.capabilities}


def test_an_ordinary_windows_session_is_available_with_the_uipi_hint():
    snapshot = _windows()
    assert set(_states(snapshot).values()) == {"available"}
    assert "UIPI" in snapshot.input.detail and "medium" in snapshot.input.detail
    assert snapshot.backend_version == "win32-test 1.2"
    assert snapshot.to_dict()["backend_version"] == "win32-test 1.2"
    assert _windows(integrity="high").input.detail == ""


def test_session_zero_supports_nothing_and_says_where_to_run_instead():
    snapshot = _windows(session_id=0)
    assert set(_states(snapshot).values()) == {"unsupported"}
    assert all(item.recovery_key == "cap_fix_win_session0" and item.recovery
               for item in snapshot.capabilities)
    assert not snapshot.input.usable


@pytest.mark.parametrize("desktop", ["Winlogon", "winlogon", "Screen-saver", ""])
def test_a_locked_workstation_needs_the_user(desktop):
    snapshot = _windows(input_desktop=desktop)
    assert set(_states(snapshot).values()) == {"needs_permission"}
    assert snapshot.capture.recovery_key == "cap_fix_win_locked"
    assert repr(desktop) in snapshot.input.detail


def test_low_integrity_cannot_inject_but_can_still_capture():
    states = _states(_windows(integrity="low"))
    assert states["input"] == "needs_permission" and states["capture"] == "available"
    assert _windows(integrity="low").input.recovery_key == "cap_fix_win_integrity"


def test_a_failed_screen_copy_is_reported_with_its_reason():
    snapshot = _windows(capture_ok=False, capture_error="BitBlt failed (error 5)")
    assert snapshot.capture.state is CapabilityStatus.NEEDS_SETUP
    assert "error 5" in snapshot.capture.detail
    assert snapshot.input.state is CapabilityStatus.AVAILABLE


def test_no_hook_access_blocks_recording_and_the_stop_key_only():
    states = _states(_windows(hook_access=False))
    assert states == {"input": "available", "capture": "available",
                      "recording": "needs_permission", "stop_shortcut": "needs_permission"}


def test_what_could_not_be_read_is_unknown_never_available():
    snapshot = probe_capabilities(BackendContext(
        platform="win32", windows_facts=WindowsFacts, backend_version=lambda _b: ""))
    assert set(_states(snapshot).values()) == {"unknown"}
    assert all(item.detail for item in snapshot.capabilities)
    assert snapshot.backend_version == ""
    partial = _states(_windows(capture_ok=None, hook_access=None))
    assert partial == {"input": "available", "capture": "unknown",
                       "recording": "unknown", "stop_shortcut": "unknown"}


def test_macos_permissions_map_to_their_settings_panes():
    snapshot = _mac(accessibility=True, screen_recording=False, input_monitoring=False)
    assert _states(snapshot) == {
        "input": "available", "capture": "needs_permission",
        "recording": "needs_permission", "stop_shortcut": "needs_permission"}
    assert snapshot.capture.recovery_key == "cap_fix_mac_screen_recording"
    assert "Screen Recording" in snapshot.capture.recovery
    assert snapshot.get("recording").recovery_key == "cap_fix_mac_input_monitoring"
    assert snapshot.input.backend == "quartz"
    assert snapshot.backend_version == "quartz-test 3.4"
    denied = _mac(accessibility=False)
    assert denied.input.state is CapabilityStatus.NEEDS_PERMISSION
    assert denied.input.recovery_key == "cap_fix_mac_accessibility"
    assert set(_states(_mac()).values()) == {"unknown"}


def test_only_preflight_calls_are_made_on_macos(monkeypatch):
    called = []

    class _Module:
        @staticmethod
        def AXIsProcessTrusted():
            called.append("AXIsProcessTrusted")
            return 1

        @staticmethod
        def CGPreflightScreenCaptureAccess():
            called.append("CGPreflightScreenCaptureAccess")
            return False

        @staticmethod
        def CGRequestScreenCaptureAccess():  # the prompting one: must never run
            called.append("CGRequestScreenCaptureAccess")
            return True

    def fake_import(name):
        if name == "ApplicationServices":
            raise ImportError(name)
        return _Module

    monkeypatch.setattr(probes.sys, "platform", "darwin")
    monkeypatch.setattr(probes.importlib, "import_module", fake_import)
    facts = probes.read_mac_facts()
    assert facts == MacFacts(accessibility=True, screen_recording=False,
                             input_monitoring=None)
    assert called == ["AXIsProcessTrusted", "CGPreflightScreenCaptureAccess"]


def test_off_their_own_platform_the_readers_read_nothing(monkeypatch):
    monkeypatch.setattr(probes.sys, "platform", "linux")
    assert probes.read_windows_facts() == WindowsFacts()
    assert probes.read_mac_facts() == MacFacts()
    assert probes.cheap_backend_version("win32") == ""
    assert probes.cheap_backend_version("quartz") == ""
    assert probes.cheap_backend_version("wayland") == ""


def test_a_query_that_raises_is_a_fact_that_was_not_read(monkeypatch):
    def boom():
        raise OSError("access denied")

    monkeypatch.setattr(probes.sys, "platform", "win32")
    for name in ("_win_integrity", "_win_session_id", "_win_input_desktop",
                 "_win_hook_access", "_win_capture"):
        monkeypatch.setattr(probes, name, boom)
    assert probes.read_windows_facts() == WindowsFacts()


def test_integrity_levels_are_named_from_their_rid():
    assert [probes._integrity_name(rid) for rid in (0, 0x1000, 0x2000, 0x2100, 0x3000, 0x4000)] == [
        "untrusted", "low", "medium", "medium", "high", "system"]


def test_linux_snapshots_carry_the_backend_version_too():
    snapshot = probe_capabilities(BackendContext(
        platform="linux", environ={"DISPLAY": ":0"}, loaded_backend="x11",
        backend_version=lambda backend: f"{backend} 0.33"))
    assert snapshot.backend_version == "x11 0.33"


def test_the_facts_are_exported_and_every_catalogue_has_the_new_advice():
    from je_auto_control.gui.language_wrapper import (
        english, japanese, simplified_chinese, traditional_chinese,
    )
    assert ac.WindowsFacts is WindowsFacts and ac.MacFacts is MacFacts
    wanted = {"cap_fix_win_session0", "cap_fix_win_locked", "cap_fix_win_integrity",
              "cap_fix_win_capture", "cap_fix_mac_accessibility",
              "cap_fix_mac_screen_recording", "cap_fix_mac_input_monitoring",
              "cap_backend_version", "cap_backend_version_unknown"}
    for module in (english, japanese, simplified_chinese, traditional_chinese):
        catalogue = next(value for value in vars(module).values()
                         if isinstance(value, dict) and "cap_fix_display" in value)
        assert not wanted - set(catalogue), module.__name__


@pytest.mark.skipif(sys.platform != "win32", reason="reads the live Windows session")
def test_the_live_windows_session_can_be_read_without_touching_it():
    facts = probes.read_windows_facts()
    assert facts.integrity in ("untrusted", "low", "medium", "high", "system")
    assert isinstance(facts.session_id, int) and facts.session_id >= 0
    assert isinstance(facts.input_desktop, str)
    assert isinstance(facts.hook_access, bool) and isinstance(facts.capture_ok, bool)
    assert probes.cheap_backend_version("win32").startswith("Windows ")
    snapshot = probe_capabilities()
    assert snapshot.platform == "win32" and len(snapshot.capabilities) == 4
    assert all(item.state is not CapabilityStatus.UNKNOWN for item in snapshot.capabilities)
    # A state that is not usable always says why.
    assert all(item.usable or item.detail for item in snapshot.capabilities)


@pytest.mark.skipif(sys.platform != "darwin", reason="asks the live macOS session")
def test_the_live_macos_session_can_be_asked_without_prompting():
    facts = probes.read_mac_facts()
    for value in (facts.accessibility, facts.screen_recording, facts.input_monitoring):
        assert value is None or isinstance(value, bool)
    snapshot = probe_capabilities()
    assert snapshot.platform == "darwin" and len(snapshot.capabilities) == 4
    assert all(item.detail for item in snapshot.capabilities)
