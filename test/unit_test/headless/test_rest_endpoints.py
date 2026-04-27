"""Tests for the REST endpoints added in rounds 23-25."""
import json
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.rest_api.rest_server import RestApiServer


_TEST_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS is out of scope here


@pytest.fixture()
def server():
    s = RestApiServer(host="127.0.0.1", port=0, enable_audit=False)
    s.start()
    yield s
    s.stop(timeout=1.0)


def _get(server, path, *, token=None):
    host, port = server.address
    url = f"{_TEST_SCHEME}://{host}:{port}{path}"
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310  # reason: localhost test server
        return response.status, json.loads(response.read().decode("utf-8"))


@pytest.mark.parametrize("path", [
    "/screen_size",
    "/mouse_position",
    "/sessions",
    "/commands",
    "/jobs",
    "/history",
])
def test_authenticated_get_endpoints_round_trip(server, path):
    status, payload = _get(server, path, token=server.token)
    assert status == 200
    assert isinstance(payload, dict)


@pytest.mark.parametrize("path", [
    "/screen_size",
    "/mouse_position",
    "/sessions",
    "/commands",
    "/jobs",
    "/history",
    "/audit/list",
    "/audit/verify",
    "/inspector/recent",
    "/inspector/summary",
    "/usb/devices",
    "/usb/events",
    "/diagnose",
    "/metrics",
    "/openapi.json",
])
def test_authenticated_endpoints_reject_anonymous(server, path):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(server, path)
    assert exc_info.value.code == 401, path


def test_screen_size_payload_shape(server):
    _, payload = _get(server, "/screen_size", token=server.token)
    assert "width" in payload and "height" in payload
    assert isinstance(payload["width"], int) and payload["width"] > 0
    assert isinstance(payload["height"], int) and payload["height"] > 0


def test_commands_payload_includes_admin_console_keys(server):
    """Round 24's AC_admin_* commands must appear in the introspection list."""
    _, payload = _get(server, "/commands", token=server.token)
    names = set(payload.get("commands", []))
    assert {"AC_admin_add_host", "AC_admin_poll",
            "AC_admin_broadcast_execute"}.issubset(names)


def test_sessions_payload_has_host_and_viewer(server):
    _, payload = _get(server, "/sessions", token=server.token)
    assert "host" in payload and "viewer" in payload
