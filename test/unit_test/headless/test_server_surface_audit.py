"""Regression tests for the server-surface defects of the 2026-09-23 audit.

The signaling server checked its shared secret in a route dependency, which
FastAPI resolves only after reading and parsing the body: a client without the
secret made it buffer a body of any size and got JSON validation errors back
instead of 401. The MCP HTTP transport refused a lower-case ``bearer`` scheme.
"""
import pytest

pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

from je_auto_control.utils.remote_desktop.signaling_server import create_app  # noqa: E402


@pytest.fixture
def client():
    return testclient.TestClient(create_app(shared_secret="s3cret", serve_web_viewer=False))


def test_a_wrong_secret_is_refused_before_the_body_is_parsed(client):
    response = client.post("/sessions/host1/offer", content=b"x" * 10,
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 401


def test_an_oversized_body_is_refused_before_it_is_read(client):
    body = b'{"sdp":"' + b"A" * (2 * 1024 * 1024) + b'"}'
    response = client.post("/sessions/host1/offer", content=body,
                           headers={"Content-Type": "application/json",
                                    "X-Signaling-Secret": "s3cret"})
    assert response.status_code == 413


def test_a_valid_offer_still_works(client):
    response = client.post("/sessions/host1/offer", json={"sdp": "v=0"},
                           headers={"X-Signaling-Secret": "s3cret"})
    assert response.status_code == 200
    fetched = client.get("/sessions/host1/offer", headers={"X-Signaling-Secret": "s3cret"})
    assert fetched.status_code == 200


def test_health_and_preflight_need_no_secret(client):
    assert client.get("/health").status_code == 200
    preflight = client.options("/sessions/host1/offer",
                               headers={"Origin": "http://x", "Access-Control-Request-Method": "POST"})
    assert preflight.status_code == 200


def test_a_lower_case_bearer_scheme_is_accepted():
    import http.client
    import json
    from je_auto_control.utils.mcp_server.http_transport import start_mcp_http_server
    server = start_mcp_http_server(host="127.0.0.1", port=0, auth_token="tok")
    try:
        host, port = server.address
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18", "capabilities": {}}})
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("POST", "/mcp", body=body, headers={"Content-Type": "application/json",
                                                         "Authorization": "bearer tok"})
        assert conn.getresponse().status == 200
        conn.close()
    finally:
        server.stop(timeout=2.0)
