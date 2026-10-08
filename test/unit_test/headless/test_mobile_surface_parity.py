"""Every mobile capability is reachable from every surface, from one table.

``wrapper.mobile_commands.MOBILE_COMMANDS`` is the single description of the
``AC_android_*`` / ``AC_ios_*`` commands. The executor, the MCP registry, the
Script Builder schema and the Mobile tab are all built from it; these tests
fail when one of them drifts. Driven against the fake backends — no device.
"""
import sys
import types

import pytest

import je_auto_control as ac
from headless._mobile_doubles import FakeAdbHost, FakeU2, FakeWda
from je_auto_control.android import UIAutomatorDevice
from je_auto_control.ios import IOSDevice
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.wrapper.device_context import (
    CAPABILITY_NAMES, DeviceContext, DevicePermissionError, DeviceUnsupportedError,
    open_device, use_device,
)
from je_auto_control.wrapper.mobile_commands import (
    DESKTOP_ONLY_FEATURES, MCP_EXCLUDED, MOBILE_COMMANDS, device_setup_report,
    mobile_capability_matrix, run_mobile_command,
)

APP = "com.example.shop"


@pytest.fixture
def adb_host(monkeypatch):
    """A fake ADB host with one attached device, ``phone``."""
    host = FakeAdbHost()
    host.add("phone").installed.add(APP)
    monkeypatch.setattr("je_auto_control.android.adb_client.subprocess.run", host.run)
    monkeypatch.setattr("je_auto_control.android.adb_client.subprocess.Popen", host.popen)
    monkeypatch.setattr("je_auto_control.android.apps._RECORDINGS", {})
    from je_auto_control.utils.executor import action_executor
    monkeypatch.setattr(action_executor, "_android_client_cache", {})
    return host


def _ios(handle):
    return open_device(DeviceContext("ios", "http://wda.test:8100"),
                       device=IOSDevice(url="http://wda.test:8100", handle=handle))


# --- one table, every surface ------------------------------------------

def _mcp_names():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    return {tool.name for tool in build_default_tool_registry()}


def _gui_commands():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.mobile_tab import MobileTab
    app = QApplication.instance() or QApplication([])
    tab = MobileTab()
    try:
        return set(tab.command_names()), [key for key, _handler in tab.menu_actions()]
    finally:
        tab.deleteLater()
        app.processEvents()


def test_every_mobile_capability_has_api_command_gui_schema():
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    mcp_names = _mcp_names()
    gui_commands, menu_keys = _gui_commands()
    missing_surface_commands = set()
    for command in MOBILE_COMMANDS:
        surfaces = {
            "executor": command.name in executor.event_dict,
            "schema": command.name in COMMAND_SPECS,
            "mcp": command.name in MCP_EXCLUDED or command.mcp_name in mcp_names,
            "gui": command.name in gui_commands,
            "api": hasattr(ac, command.api.split(".")[0])
            and command.api.split(".")[0] in ac.__all__,
        }
        missing_surface_commands |= {
            f"{command.name}:{surface}" for surface, present in surfaces.items() if not present}
    assert missing_surface_commands == set()
    assert menu_keys, "the Mobile tab must expose its commands through the Actions menu"
    # The table is the whole mobile surface: no command lives outside it.
    in_executor = {name for name in executor.event_dict
                   if name.startswith(("AC_android_", "AC_ios_"))}
    assert in_executor == {command.name for command in MOBILE_COMMANDS}
    # An excluded tool says why.
    assert all(reason for reason in MCP_EXCLUDED.values())


def test_schema_fields_match_the_command_parameters():
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    for command in MOBILE_COMMANDS:
        spec = COMMAND_SPECS[command.name]
        assert [field.name for field in spec.fields] == [p.name for p in command.params]
        assert [not field.optional for field in spec.fields] == [
            p.required for p in command.params]
        assert spec.category in ("Android", "iOS")


def test_mcp_schema_matches_the_command_parameters():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    for command in MOBILE_COMMANDS:
        if command.name in MCP_EXCLUDED:
            assert command.mcp_name not in tools
            continue
        schema = tools[command.mcp_name].input_schema
        assert set(schema["properties"]) >= {p.name for p in command.params if p.required}
        if not command.handwritten_mcp:
            assert set(schema["properties"]) == {p.name for p in command.params}
            assert schema.get("required", []) == [p.name for p in command.params if p.required]
            assert tools[command.mcp_name].annotations.read_only is command.read_only


def test_every_capability_is_covered_on_both_platforms():
    matrix = mobile_capability_matrix()
    rows = {row["capability"]: row for row in matrix["capabilities"]}
    assert set(rows) == set(CAPABILITY_NAMES)
    for name, row in rows.items():
        assert row["android"], f"no Android command uses {name}"
        assert row["ios"], f"no iOS command uses {name}"
    # Desktop-only features say what the limit is and what to use instead.
    assert DESKTOP_ONLY_FEATURES
    for row in matrix["desktop_only"]:
        assert row["limitation"] and row["alternative"]


# --- the generated commands really run ---------------------------------

def test_generated_commands_drive_the_device(adb_host, tmp_path):
    phone = adb_host.devices["phone"]
    handle = FakeU2()
    session = open_device(DeviceContext("android", "phone", adb_path="fake-adb"),
                          ui_device=UIAutomatorDevice(handle=handle))
    with use_device(session):
        result = executor.execute_action([
            ["AC_android_launch_app", {"app_id": APP}],
            ["AC_android_wait_for_app", {"app_id": APP, "timeout_s": 1.0}],
            ["AC_android_long_press", {"x": 10, "y": 20, "duration_s": 0.5}],
            ["AC_android_drag", [1, 2, 3, 4]],
            ["AC_android_pinch", {"x": 500, "y": 800, "scale": 2.0}],
            ["AC_android_set_clipboard", {"text": "hi"}],
            ["AC_android_stop_app", {"app_id": APP}],
        ], raise_on_error=True)
    assert list(result.values())[0] == "foreground"
    assert list(result.values())[-1] == "not_running"
    assert phone.input_calls == [
        f"monkey -p {APP} -c android.intent.category.LAUNCHER 1",
        "input swipe 10 20 10 20 500",
        "input draganddrop 1 2 3 4 1000",
        f"am force-stop {APP}",
    ]
    assert handle.clipboard == "hi"
    # Without a bound session the command opens its own from serial / adb_path.
    info = run_mobile_command("AC_android_screen_info",
                              {"serial": "phone", "adb_path": "fake-adb"})
    assert info["point_size"] == [1080, 1920]


def test_unknown_parameters_and_commands_are_rejected(adb_host):
    with pytest.raises(TypeError):
        run_mobile_command("AC_android_long_press", {"x": 1, "y": 2, "bogus": 3})
    with pytest.raises(TypeError):
        run_mobile_command("AC_android_long_press", {"x": 1})
    with pytest.raises(ac.DeviceError):
        run_mobile_command("AC_click_mouse", {})
    assert adb_host.devices["phone"].input_calls == []


def test_ios_command_without_a_backend_feature_says_why(tmp_path):
    handle = FakeWda()
    with use_device(_ios(handle)):
        with pytest.raises(DeviceUnsupportedError) as caught:
            run_mobile_command("AC_ios_install_app", {"path": str(tmp_path / "a.ipa")})
        assert caught.value.reason and caught.value.alternative
        assert run_mobile_command("AC_ios_long_press", {"x": 1, "y": 2}) is None
    assert handle.input_calls == [{"op": "tap_hold", "x": 1, "y": 2, "duration": 1.0}]


def test_mcp_tool_calls_the_same_handler(adb_host):
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    tools["ac_android_long_press"].invoke(
        {"x": 7, "y": 8, "serial": "phone", "adb_path": "fake-adb"})
    tools["ac_android_tap"].invoke({"x": 1, "y": 2, "serial": "phone", "adb_path": "fake-adb"})
    assert adb_host.devices["phone"].input_calls == [
        "input swipe 7 8 7 8 1000", "input tap 1 2"]


# --- setup reports -----------------------------------------------------

def test_wda_remote_endpoint_setup(monkeypatch):
    handle = FakeWda()
    session = open_device(
        DeviceContext("ios", "http://192.168.1.20:8100"),
        device=IOSDevice(url="http://192.168.1.20:8100", handle=handle))
    device_setup_report = ac.device_setup_report(session)
    assert device_setup_report.backend_version
    assert device_setup_report.backend == "wda"
    assert device_setup_report.backend_version == "8.5.2"
    assert device_setup_report.os_version == "17.4"
    assert device_setup_report.state == "available"
    assert handle.input_calls == []
    assert device_setup_report.to_dict()["capabilities"]["install"]["state"] == "needs_dependency"

    # The URL in the context is the endpoint the client is built for.
    seen = []
    fake_wda = types.ModuleType("wda")
    fake_wda.Client = lambda url: seen.append(url) or handle
    monkeypatch.setitem(sys.modules, "wda", fake_wda)
    remote = open_device(DeviceContext("ios", "http://10.0.0.7:8100"))
    assert ac.device_setup_report(remote).backend_version == "8.5.2"
    assert seen == ["http://10.0.0.7:8100"]

    # An endpoint that does not answer is reported, with the reason, not raised.
    class _Down(FakeWda):
        def status(self):
            raise OSError("connection refused")

    down = ac.device_setup_report(_ios(_Down()))
    assert down.state == "needs_dependency"
    assert "connection refused" in down.reason
    assert down.backend_version == ""


def test_android_setup_report(adb_host):
    report = device_setup_report(
        open_device(DeviceContext("android", "phone", adb_path="fake-adb")))
    assert report.backend == "adb"
    assert report.backend_version.startswith("1.0.41")
    assert report.os_version == "14"
    assert report.state == "available"
    assert adb_host.devices["phone"].input_calls == []


def test_android_authorization_error(adb_host):
    locked = adb_host.add("locked", state="unauthorized")
    address = {"serial": "locked", "adb_path": "fake-adb"}
    for name, params in (("AC_android_tap", {"x": 1, "y": 2}),
                         ("AC_android_long_press", {"x": 1, "y": 2}),
                         ("AC_android_type_text", {"text": "hello"}),
                         ("AC_android_launch_app", {"app_id": APP})):
        with pytest.raises(DevicePermissionError):
            run_mobile_command(name, {**params, **address})
    unauthorized_input_calls = locked.input_calls
    assert unauthorized_input_calls == []
    report = run_mobile_command("AC_android_device_info", address)
    assert report["state"] == "needs_permission"
    assert "USB debugging" in report["reason"]
    assert report["capabilities"]["input"]["state"] == "needs_permission"


# --- the tab -----------------------------------------------------------

def test_mobile_tab_is_registered_once_and_translated():
    from je_auto_control.gui.tab_registry import TAB_SPECS
    rows = [spec for spec in TAB_SPECS if spec.key == "mobile"]
    assert len(rows) == 1
    assert (rows[0].module, rows[0].class_name) == ("je_auto_control.gui.mobile_tab", "MobileTab")
    from je_auto_control.gui.language_wrapper import (
        english, japanese, simplified_chinese, traditional_chinese,
    )
    catalogues = (english.english_word_dict, japanese.japanese_word_dict,
                  simplified_chinese.simplified_chinese_word_dict,
                  traditional_chinese.traditional_chinese_word_dict)
    keys = {key for key in catalogues[0] if key.startswith("mob_")} | {"tab_mobile"}
    assert len(keys) > 5
    for catalogue in catalogues:
        assert keys <= set(catalogue)


def test_mobile_tab_runs_a_command_through_the_headless_api(adb_host):
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.mobile_tab import MobileTab
    app = QApplication.instance() or QApplication([])
    tab = MobileTab()
    try:
        tab.set_target("android", "phone", adb_path="fake-adb")
        tab.set_command("AC_android_long_press", {"x": 3, "y": 4})
        actions = dict(tab.menu_actions())
        actions["mob_run"]()
        assert adb_host.devices["phone"].input_calls == ["input swipe 3 4 3 4 1000"]
        actions["mob_probe"]()
        assert tab.capability_rows()["input"] == "available"
        tab.set_command("AC_android_long_press", {"x": 3})
        actions["mob_run"]()
        assert "y" in tab.result_text()
    finally:
        tab.deleteLater()
        app.processEvents()
