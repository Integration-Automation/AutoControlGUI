"""REST server defects from the 2026-09-24 audit.

The POST body was read and parsed before the auth gate, so unauthenticated
clients got 400 (never 401 / 429) and were never rate-limited or locked out;
eight bad requests from anyone on the same IP locked the real token holder
out; and a corrupt audit database made ``RestApiServer()`` itself raise.
No real action runs: the ``/execute`` handler is replaced by a fake.
"""
import http.client
import json

import pytest

from je_auto_control.utils.remote_desktop import audit_log
from je_auto_control.utils.rest_api import rest_server
from je_auto_control.utils.rest_api.rest_auth import RestAuthGate
from je_auto_control.utils.rest_api.rest_server import RestApiServer

TOKEN = "test-token-1"


@pytest.fixture
def server(monkeypatch):
    calls = []
    monkeypatch.setitem(rest_server._POST_ROUTES, "/execute",
                        lambda ctx: calls.append(ctx.body) or (200, {"ok": True}))
    srv = RestApiServer(host="127.0.0.1", port=0, token=TOKEN, enable_audit=False)
    srv.start()
    srv.calls = calls  # type: ignore[attr-defined]
    yield srv
    srv.stop()


def _post(server, body, token=None):
    connection = http.client.HTTPConnection(*server.address, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    try:
        connection.request("POST", "/execute", body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_an_unauthenticated_bad_body_gets_401_not_400(server):
    status, _ = _post(server, b"{not json", token=None)
    assert status == 401
    assert server.calls == []


def test_unauthenticated_bodies_count_against_the_rate_limit(server):
    statuses = {_post(server, b"x" * 1000)[0] for _ in range(40)}
    assert 429 in statuses and 400 not in statuses


def test_the_authorised_body_still_reaches_the_handler(server):
    status, body = _post(server, json.dumps({"actions": []}).encode(), token=TOKEN)
    assert status == 200 and json.loads(body) == {"ok": True}
    assert server.calls == [{"actions": []}]


def test_a_valid_token_is_never_locked_out():
    gate = RestAuthGate(expected_token=TOKEN, requests_per_minute=6000, burst=100)
    for _ in range(10):
        assert gate.check(client_ip="127.0.0.1", header_value="Bearer wrong") in (
            "unauthorized", "locked_out")
    assert gate.check(client_ip="127.0.0.1", header_value="Bearer wrong") == "locked_out"
    assert gate.check(client_ip="127.0.0.1", header_value=f"Bearer {TOKEN}") == "ok"


def test_a_corrupt_audit_database_does_not_stop_the_server(tmp_path, monkeypatch):
    broken = tmp_path / "audit.db"
    broken.write_bytes(b"this is not a sqlite database" * 100)
    monkeypatch.setattr(audit_log, "default_audit_log", lambda: audit_log.AuditLog(broken))
    server = RestApiServer(host="127.0.0.1", port=0, token=TOKEN, enable_audit=True)
    assert server._audit_log is None
