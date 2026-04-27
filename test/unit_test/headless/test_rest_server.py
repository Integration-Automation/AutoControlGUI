"""Tests for the REST API server: auth gate + JSON dispatch."""
import json
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.rest_api.rest_server import RestApiServer


_TEST_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS is out of scope here


@pytest.fixture()
def rest_server():
    server = RestApiServer(host="127.0.0.1", port=0, enable_audit=False)
    server.start()
    yield server
    server.stop(timeout=1.0)


def _request(server, path, *, method="GET", body=None, token=None):
    host, port = server.address
    url = f"{_TEST_SCHEME}://{host}:{port}{path}"
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310  # reason: localhost test server
        return response.status, json.loads(response.read().decode("utf-8"))


def test_health_endpoint_unauthenticated(rest_server):
    """/health is intentionally public so probes can run without a token."""
    status, payload = _request(rest_server, "/health")
    assert status == 200
    assert payload == {"status": "ok"}


def test_authenticated_endpoint_rejects_missing_token(rest_server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _request(rest_server, "/jobs")
    assert exc_info.value.code == 401


def test_authenticated_endpoint_rejects_wrong_token(rest_server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _request(rest_server, "/jobs", token="not-the-token")
    assert exc_info.value.code == 401


def test_jobs_endpoint_with_token(rest_server):
    status, payload = _request(rest_server, "/jobs", token=rest_server.token)
    assert status == 200
    assert isinstance(payload.get("jobs"), list)


def test_execute_rejects_missing_actions(rest_server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _request(rest_server, "/execute", method="POST",
                 body={}, token=rest_server.token)
    assert exc_info.value.code == 400
    payload = json.loads(exc_info.value.read().decode("utf-8"))
    assert "actions" in payload.get("error", "")


def test_unknown_path_returns_404(rest_server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _request(rest_server, "/nope", token=rest_server.token)
    assert exc_info.value.code == 404


def test_handler_crash_returns_500_not_dropped(rest_server):
    """Sending an action list that raises must produce JSON, not RST."""
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _request(rest_server, "/execute", method="POST",
                 body={"actions": []}, token=rest_server.token)
    assert exc_info.value.code == 500
    payload = json.loads(exc_info.value.read().decode("utf-8"))
    assert "error" in payload


def test_metrics_endpoint_returns_prometheus_text(rest_server):
    """Verify content-type and the presence of expected metric families."""
    host, port = rest_server.address
    req = urllib.request.Request(
        f"{_TEST_SCHEME}://{host}:{port}/metrics",
        headers={"Authorization": f"Bearer {rest_server.token}"},
    )
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310  # reason: localhost test server
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert response.headers.get("Content-Type", "").startswith("text/plain")
    for needle in (
        "autocontrol_rest_uptime_seconds",
        "autocontrol_rest_failed_auth_total",
        "autocontrol_rest_requests_total",
    ):
        assert needle in body, f"missing {needle!r}"


def test_metrics_endpoint_requires_token(rest_server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        host, port = rest_server.address
        urllib.request.urlopen(  # nosec B310  # reason: localhost test server
            f"{_TEST_SCHEME}://{host}:{port}/metrics", timeout=3,
        )
    assert exc_info.value.code == 401
