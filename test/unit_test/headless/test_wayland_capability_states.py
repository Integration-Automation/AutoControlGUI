"""Permission boundaries and passive Wayland capability reporting."""
import os
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from je_auto_control.linux_wayland import _select_input, keyboard, libei, mouse, oeffis, portal
from je_auto_control.utils.exception.exceptions import AutoControlException


def test_cancel_does_not_fallback_silently(monkeypatch):
    """A declined portal must never cause CLI input or a repeated dialog."""
    from je_auto_control.linux_wayland.permission import WaylandPermissionRequired

    backend = MagicMock()
    backend.connect.side_effect = WaylandPermissionRequired("input", "permission denied")
    libei.reset_default_backend()
    monkeypatch.setattr(libei, "LibeiBackend", lambda: backend)
    monkeypatch.setattr(_select_input, "select_input_backend", lambda: "libei")
    run = MagicMock()
    monkeypatch.setattr(keyboard, "_run", run)
    try:
        for _ in range(2):
            with pytest.raises(WaylandPermissionRequired) as canceled:
                keyboard.press_key(28)
            assert canceled.value.state == "needs_permission"
        assert backend.connect.call_count == 1
        run.assert_not_called()
    finally:
        libei.reset_default_backend()


def test_revoked_session_cannot_send(monkeypatch):
    """A paused/removed sender cannot silently switch input transports."""
    backend = MagicMock()
    backend.set_position.side_effect = libei.LibeiUnavailable("device paused")
    monkeypatch.setattr(mouse, "_try_libei", lambda: backend)
    monkeypatch.setattr(mouse, "_require_ydotool", lambda: "/usr/bin/ydotool")
    monkeypatch.setattr(mouse, "_apply_accel_policy", lambda: None)
    monkeypatch.setattr(mouse, "_ydotool_point", lambda x, y: (x, y))
    run = MagicMock()
    monkeypatch.setattr(mouse, "_run", run)
    with pytest.raises(AutoControlException):
        mouse.set_position(100, 50)
    assert run.call_count == 0


def test_xwayland_scope_is_explicit():
    from je_auto_control.wrapper.capabilities import BackendContext, probe_capabilities

    snapshot = probe_capabilities(BackendContext(
        platform="linux", display_server="x11", environ={"WAYLAND_DISPLAY": "wayland-0"},
    ))
    assert snapshot.input.desktop_wide is False
    assert snapshot.capture.desktop_wide is False
    assert "XWayland" in snapshot.capture.reason


def test_probe_never_connects_or_requests_authorization(monkeypatch):
    from je_auto_control.wrapper import capabilities

    forbidden = MagicMock(side_effect=AssertionError("probe requested permission"))
    monkeypatch.setattr(libei, "connected_backend", forbidden)
    monkeypatch.setattr(oeffis, "connect_eis_fd", forbidden)
    monkeypatch.setattr(portal, "capture_png", forbidden)
    monkeypatch.setattr(capabilities, "find_library", lambda name: "/lib/" + name)
    monkeypatch.setattr(capabilities.shutil, "which", lambda name: None)
    snapshot = capabilities.probe_capabilities(capabilities.BackendContext(
        platform="linux", display_server="wayland",
        environ={"DBUS_SESSION_BUS_ADDRESS": "unix:path=/fake"},
    ))
    assert snapshot.input.state == "needs_permission"
    assert snapshot.capture.state == "needs_permission"
    forbidden.assert_not_called()


def test_portal_cancel_is_a_typed_permission_state():
    from je_auto_control.linux_wayland.permission import WaylandPermissionRequired

    with pytest.raises(WaylandPermissionRequired) as error:
        portal._uri_from_response([1, {}])
    assert error.value.capability == "capture"
    assert error.value.state == "needs_permission"


def test_portal_timeout_closes_outstanding_request():
    bus = MagicMock()
    bus.sender_token = "1_2"
    bus.call.return_value = ["/org/freedesktop/portal/desktop/request/1_2/fake"]
    bus.wait_for_signal.side_effect = portal._dbus_client.DBusError("timeout")
    with pytest.raises(AutoControlException):
        portal._request_and_await(bus, 0.01)
    assert any(call.args[3] == "Close" for call in bus.call.call_args_list)


def test_live_portal_revocation_prevents_native_emission(monkeypatch):
    from je_auto_control.linux_wayland.permission import WaylandPermissionRequired

    native = MagicMock()
    grant = MagicMock()
    grant.oeffis_get_fd.return_value = 7
    grant.oeffis_get_event.return_value = oeffis.OEFFIS_EVENT_CLOSED
    grant.oeffis_get_error_message.return_value = b"revoked"
    backend = libei.LibeiBackend(symbols=native)
    backend._ei = 1
    backend._session = oeffis._Session(grant, 2)
    monkeypatch.setattr(oeffis.select, "select", lambda *args: ([7], [], []))
    monkeypatch.setattr(backend, "_pump", lambda timeout: None)
    for _ in range(2):
        with pytest.raises(WaylandPermissionRequired, match="revoked"):
            backend.press_key(28)
    native.ei_device_keyboard_key.assert_not_called()
    native.ei_device_frame.assert_not_called()
    assert grant.oeffis_unref.call_count == 1


def test_stop_blocks_text_until_explicit_retry(monkeypatch):
    from je_auto_control.linux_wayland.permission import WaylandPermissionRequired

    run = MagicMock()
    monkeypatch.delenv("JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND", raising=False)
    monkeypatch.setattr(keyboard, "_run", run)
    monkeypatch.setattr(keyboard, "_require", lambda *args: "/usr/bin/wtype")
    libei.reset_default_backend()
    try:
        libei.stop_input_control()
        with pytest.raises(WaylandPermissionRequired, match="stopped by the operator"):
            keyboard.write("hello")
        run.assert_not_called()
        libei.reset_default_backend()
        keyboard.write("hello")
        assert run.call_count == 1
    finally:
        libei.reset_default_backend()


def test_passive_diagnostics_skip_active_checks(monkeypatch):
    from je_auto_control.utils.diagnostics import diagnostics

    forbidden = MagicMock(side_effect=AssertionError("active diagnostic executed"))
    forbidden.__name__ = "_check_screenshot"
    monkeypatch.setattr(diagnostics, "_check_screenshot", forbidden)
    monkeypatch.setattr(diagnostics, "_check_mouse", forbidden)
    monkeypatch.setattr(diagnostics, "_ALL_CHECKS", (forbidden, diagnostics._check_backend_capabilities))
    report = diagnostics.run_diagnostics(include_active=False)
    forbidden.assert_not_called()
    assert any(check.name == "backend_capabilities" for check in report.checks)


def test_beta_probe_keeps_headless_import_qt_free():
    code = """
import sys
from je_auto_control.api.capabilities import probe_capabilities
probe_capabilities()
assert not any(name.startswith('PySide6') for name in sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_ac_and_mcp_share_passive_capability_snapshot():
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.utils.rbac.authorization import required_capability
    from je_auto_control.utils.rbac.users import Capability
    from je_auto_control.wrapper.capabilities import probe_capabilities

    tools = {tool.name: tool for tool in build_default_tool_registry()}
    tool = tools["ac_probe_capabilities"]
    assert executor.event_dict["AC_probe_capabilities"]() == probe_capabilities().to_dict()
    assert tool.handler() == probe_capabilities().to_dict()
    assert tool.annotations.read_only is True
    assert required_capability("AC_probe_capabilities") == Capability.READ_SCREEN


def test_gui_diagnostics_stop_retry_and_passive_refresh():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    code = """
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from je_auto_control.gui import diagnostics_tab as gui
from je_auto_control.linux_wayland import _detect, libei
from je_auto_control.utils.diagnostics import DiagnosticsReport
app = QApplication([])
calls = []
def report(**kwargs):
    calls.append(kwargs)
    return DiagnosticsReport([])
with patch.object(gui, 'sys', SimpleNamespace(platform='linux')), \
     patch.object(_detect, 'is_wayland_session', return_value=True), \
     patch.object(gui, 'run_diagnostics', side_effect=report):
    tab = gui.DiagnosticsTab()
    actions = dict(tab.menu_actions())
    actions['diag_stop_input']()
    assert libei.input_permission_status()[0] == 'needs_permission'
    actions['diag_retry_input']()
    assert libei.input_permission_status() is None
    assert calls == [{'include_active': False}] * 3
    tab.deleteLater()
    app.processEvents()
"""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                            text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
