"""Tests for the web admin dashboard static assets (round 29)."""
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


def _get(server, path):
    host, port = server.address
    req = urllib.request.Request(
        f"{_TEST_SCHEME}://{host}:{port}{path}", method="GET",
    )
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310  # reason: localhost test server
        return (response.status,
                response.headers.get("Content-Type", ""),
                response.read())


def test_dashboard_page_is_unauthenticated(server):
    """Page itself must be reachable without a token (it's just an HTML shell)."""
    status, ctype, body = _get(server, "/dashboard")
    assert status == 200
    assert ctype.startswith("text/html")
    assert b"<title>AutoControl Dashboard</title>" in body


def test_dashboard_css_asset(server):
    status, ctype, _body = _get(server, "/dashboard/app.css")
    assert status == 200
    assert ctype.startswith("text/css")


def test_dashboard_js_asset(server):
    status, ctype, body = _get(server, "/dashboard/app.js")
    assert status == 200
    assert ctype.startswith("application/javascript")
    assert b"POLL_MS" in body


@pytest.mark.parametrize("evil_path", [
    "/dashboard/..%2F..%2F..%2Fetc%2Fpasswd",
    "/dashboard/../rest_server.py",
    "/dashboard/.hidden",
    "/dashboard/missing.html",
    "/dashboard/sub/path.html",
])
def test_path_traversal_attempts_return_404(server, evil_path):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(server, evil_path)
    assert exc_info.value.code == 404


def test_dashboard_does_not_leak_python_source(server):
    """Make sure asset whitelist blocks .py and other non-asset extensions."""
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(server, "/dashboard/rest_server.py")
    assert exc_info.value.code == 404
