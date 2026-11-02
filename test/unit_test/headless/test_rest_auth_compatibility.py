"""Legacy REST gates remain usable without bypassing store-backed identity."""
import http.client
import json
import os
from types import SimpleNamespace

import pytest

from je_auto_control.utils.rbac.authorization import USERS_ENV
from je_auto_control.utils.rbac.users import UserStore
from je_auto_control.utils.rest_api.rest_auth import AuthResult
from je_auto_control.utils.rest_api.rest_registry import _RestApiRegistry
from je_auto_control.utils.rest_api.rest_server import RestApiServer


@pytest.fixture(autouse=True)
def no_ambient_store(monkeypatch):
    monkeypatch.delenv(USERS_ENV, raising=False)


def _get(server, path="/commands"):
    conn = http.client.HTTPConnection(*server.address, timeout=5)
    try:
        conn.request("GET", path, headers={"Authorization": "Bearer legacy"})
        reply = conn.getresponse()
        return reply.status, json.loads(reply.read())
    finally:
        conn.close()


class LegacyGate:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = []

    def check(self, **kwargs):
        self.calls.append(kwargs)
        return self.verdict


@pytest.mark.parametrize("verdict,expected", [
    ("ok", 200), ("unauthorized", 401), ("rate_limited", 429), ("locked_out", 429),
])
def test_check_only_gate_works_with_shared_auth(verdict, expected):
    server = RestApiServer(port=0, enable_audit=False)
    gate = LegacyGate(verdict)
    server._auth = gate
    server.start()
    try:
        status, _ = _get(server)
        assert status == expected
        assert gate.calls == [{"client_ip": "127.0.0.1", "header_value": "Bearer legacy"}]
    finally:
        server.stop()


@pytest.mark.parametrize("modern", [False, True])
def test_identityless_custom_gate_cannot_bypass_rbac(tmp_path, modern):
    users = UserStore(tmp_path / "users.json")
    users.add_user(user_id="viewer", display_name="Viewer", role="viewer")
    server = RestApiServer(port=0, enable_audit=False, user_store=users)
    server._auth = (SimpleNamespace(authenticate=lambda **_kwargs: AuthResult("ok"))
                    if modern else LegacyGate("ok"))
    server.start()
    try:
        assert _get(server)[0] == 401
    finally:
        server.stop()


@pytest.mark.parametrize("rbac", [False, True])
def test_registry_exposes_auth_mode_and_only_a_usable_shared_token(rbac, tmp_path):
    registry = _RestApiRegistry()
    assert registry.status()["rbac_enabled"] is False
    users = UserStore(tmp_path / "users.json") if rbac else None
    status = registry.start(port=0, token="shared", enable_audit=False, user_store=users)
    try:
        assert status["rbac_enabled"] is rbac
        assert status["token"] == (None if rbac else "shared")
        assert registry.server.token == "shared"  # preserve the Python server property
    finally:
        registry.stop()
    assert registry.status()["rbac_enabled"] is False


def test_registry_reports_environment_configured_rbac(tmp_path, monkeypatch):
    monkeypatch.setenv(USERS_ENV, str(tmp_path / "users.json"))
    registry = _RestApiRegistry()
    try:
        status = registry.start(port=0, enable_audit=False)
        assert status["rbac_enabled"] is True and status["token"] is None
    finally:
        registry.stop()


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    return widgets.QApplication.instance() or widgets.QApplication([])


@pytest.mark.parametrize("rbac", [False, True])
def test_gui_copies_shared_token_only_when_it_can_be_used(qapp, monkeypatch, rbac):
    from je_auto_control.gui import rest_api_tab
    copied = []
    monkeypatch.setattr(rest_api_tab.rest_api_registry, "status", lambda: {
        "running": True, "url": "http://127.0.0.1:9939", "token": None if rbac else "shared",
        "rbac_enabled": rbac,
    })
    monkeypatch.setattr(rest_api_tab.QGuiApplication, "clipboard", lambda: SimpleNamespace(setText=copied.append))
    tab = rest_api_tab.RestApiTab()
    try:
        assert tab._token_input.isEnabled() is not rbac
        assert tab._token_value.text() == ("-" if rbac else "shared")
        tab._on_copy_token()
        assert copied == ([] if rbac else ["shared"])
        if rbac:
            assert "RBAC" in tab._status_label.text()
    finally:
        tab.deleteLater()


def test_gui_restores_shared_token_controls_after_rbac_stops(qapp, monkeypatch):
    from je_auto_control.gui import rest_api_tab
    status = {"running": True, "url": "http://127.0.0.1:9939", "token": None, "rbac_enabled": True}
    monkeypatch.setattr(rest_api_tab.rest_api_registry, "status", lambda: status)
    tab = rest_api_tab.RestApiTab()
    try:
        assert not tab._token_input.isEnabled()
        status.update(running=False, rbac_enabled=False)
        tab._refresh_status()
        assert tab._token_input.isEnabled() and tab._token_value.text() == "-"
        status.update(running=True, token="new-shared")
        tab._refresh_status()
        assert tab._token_value.text() == "new-shared"
    finally:
        tab.deleteLater()
