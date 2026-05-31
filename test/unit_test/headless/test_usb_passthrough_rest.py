"""Tests for the /usb/passthrough, /usb/acl, /usb/loopback, /usb/remote REST API."""
import json
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.rest_api.rest_server import RestApiServer
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbBackend,
)

_TEST_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server
_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123")


@pytest.fixture(autouse=True)
def isolated_usb(monkeypatch, tmp_path):
    """Temp ACL + fake backend so REST calls never touch real hardware/ACL."""
    monkeypatch.setattr(
        "je_auto_control.utils.usb.passthrough.acl.default_acl_path",
        lambda: tmp_path / "usb_acl.json",
    )
    monkeypatch.setattr(
        "je_auto_control.utils.usb.passthrough.loopback.default_passthrough_backend",
        lambda: FakeUsbBackend(devices=[_SAMPLE]),
    )


@pytest.fixture()
def server():
    s = RestApiServer(host="127.0.0.1", port=0, enable_audit=False)
    s.start()
    yield s
    s.stop(timeout=1.0)


def _get(server, path, *, token=None):
    host, port = server.address
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(
        f"{_TEST_SCHEME}://{host}:{port}{path}", headers=headers, method="GET",
    )
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310
        return response.status, json.loads(response.read().decode("utf-8"))


def _post(server, path, body, *, token=None):
    host, port = server.address
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{_TEST_SCHEME}://{host}:{port}{path}", data=data,
        headers=headers, method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310
        return response.status, json.loads(response.read().decode("utf-8"))


def test_passthrough_status_get(server):
    status, payload = _get(server, "/usb/passthrough/status", token=server.token)
    assert status == 200
    assert "enabled" in payload


def test_acl_add_then_list(server):
    status, payload = _post(server, "/usb/acl/add", {
        "vendor_id": "1050", "product_id": "0407", "allow": True,
    }, token=server.token)
    assert status == 200 and payload["added"] is True
    status, listed = _get(server, "/usb/acl", token=server.token)
    assert status == 200
    assert listed["default"] == "deny"
    assert any(r["vendor_id"] == "1050" for r in listed["rules"])


def test_acl_add_missing_params_is_400(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/usb/acl/add", {"vendor_id": "1050"}, token=server.token)
    assert exc.value.code == 400


def test_acl_default_validates_policy(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/usb/acl/default", {"policy": "maybe"}, token=server.token)
    assert exc.value.code == 400
    status, payload = _post(server, "/usb/acl/default", {"policy": "allow"},
                            token=server.token)
    assert status == 200 and payload["default"] == "allow"


def test_loopback_list_and_open(server):
    _post(server, "/usb/acl/add", {"vendor_id": "1050", "product_id": "0407"},
          token=server.token)
    status, payload = _get(server, "/usb/loopback/devices", token=server.token)
    assert status == 200
    assert [d["vendor_id"] for d in payload["devices"]] == ["1050"]
    status, opened = _post(server, "/usb/loopback/open", {
        "vendor_id": "1050", "product_id": "0407", "serial": "ABC123",
    }, token=server.token)
    assert status == 200 and opened["ok"] is True
    assert "descriptor" in opened


def test_remote_devices_without_session_is_500(server):
    from je_auto_control.utils.remote_desktop.registry import registry
    registry._webrtc_viewer = None  # noqa: SLF001
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/usb/remote/devices", token=server.token)
    assert exc.value.code == 500


def test_passthrough_endpoints_reject_anonymous(server):
    for path in ("/usb/passthrough/status", "/usb/acl",
                 "/usb/loopback/devices", "/usb/remote/devices"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(server, path)
        assert exc.value.code == 401, path
