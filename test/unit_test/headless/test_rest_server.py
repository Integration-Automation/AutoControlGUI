"""Tests for the REST API server."""
import json
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.rest_api.rest_server import RestApiServer


@pytest.fixture()
def rest_server():
    server = RestApiServer(host="127.0.0.1", port=0)
    server.start()
    yield server
    server.stop(timeout=1.0)


_TEST_SCHEME = "http"  # NOSONAR: S5332  # reason: localhost-only ephemeral test server; TLS is out of scope here


def _request(server, path, method="GET", body=None):
    host, port = server.address
    url = f"{_TEST_SCHEME}://{host}:{port}{path}"
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310  # reason: localhost test server
        return response.status, json.loads(response.read().decode("utf-8"))


def test_health_endpoint(rest_server):
    status, payload = _request(rest_server, "/health")
    assert status == 200
    assert payload == {"status": "ok"}


def test_jobs_endpoint_returns_list(rest_server):
    status, payload = _request(rest_server, "/jobs")
    assert status == 200
    assert isinstance(payload.get("jobs"), list)


def test_execute_rejects_missing_actions(rest_server):
    try:
        _request(rest_server, "/execute", method="POST", body={})
    except urllib.error.HTTPError as error:
        assert error.code == 400
        payload = json.loads(error.read().decode("utf-8"))
        assert "actions" in payload.get("error", "")
    else:
        pytest.fail("expected 400 response")


def test_unknown_path_returns_404(rest_server):
    try:
        _request(rest_server, "/nope")
    except urllib.error.HTTPError as error:
        assert error.code == 404
    else:
        pytest.fail("expected 404 response")
