"""Headless tests for the HTTP/API request action.

No real network is used: urllib.request.urlopen is monkeypatched with a
fake response/HTTPError so the tests stay deterministic and offline.
"""
import io
import json
import urllib.error

import pytest

import je_auto_control as ac
from je_auto_control.utils.http_client import http_client


class _FakeResponse:
    def __init__(self, status, body, headers=None, url="https://x"):
        self.status = status
        self._body = body.encode("utf-8") if isinstance(body, str) else body
        self.headers = headers or {"Content-Type": "application/json"}
        self.url = url

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _capture_request(captured):
    def fake_urlopen(request, timeout=None):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse(200, json.dumps({"ok": True}))
    return fake_urlopen


def test_get_parses_json_and_status(monkeypatch):
    monkeypatch.setattr(http_client.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResponse(
                            200, '{"hello": "world"}'))
    resp = http_client.http_request("https://api.example/data")
    assert resp["status"] == 200
    assert resp["ok"] is True
    assert resp["json"] == {"hello": "world"}
    assert resp["text"] == '{"hello": "world"}'


def test_post_sends_json_body_and_content_type(monkeypatch):
    captured = {}
    monkeypatch.setattr(http_client.urllib.request, "urlopen",
                        _capture_request(captured))
    http_client.http_request("https://api.example/items", method="post",
                             json_body={"name": "Sam"})
    request = captured["request"]
    assert request.method == "POST"
    assert request.data == b'{"name": "Sam"}'
    assert request.headers.get("Content-type") == "application/json"


def test_bearer_auth_header(monkeypatch):
    captured = {}
    monkeypatch.setattr(http_client.urllib.request, "urlopen",
                        _capture_request(captured))
    http_client.http_request("https://api.example", auth={
        "type": "bearer", "token": "abc123"})
    assert captured["request"].headers.get("Authorization") == "Bearer abc123"


def test_basic_auth_header(monkeypatch):
    captured = {}
    monkeypatch.setattr(http_client.urllib.request, "urlopen",
                        _capture_request(captured))
    http_client.http_request("https://api.example", auth={
        "type": "basic", "username": "u", "password": "p"})
    # base64("u:p") == "dTpw"
    assert captured["request"].headers.get("Authorization") == "Basic dTpw"


def test_unknown_auth_type_rejected(monkeypatch):
    monkeypatch.setattr(http_client.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResponse(200, "{}"))
    with pytest.raises(ValueError):
        http_client.http_request("https://x", auth={"type": "oauth"})


def test_http_error_is_returned_not_raised(monkeypatch):
    def raise_http_error(req, timeout=None):
        raise urllib.error.HTTPError(
            "https://x", 404, "Not Found", {"Content-Type": "text/plain"},
            io.BytesIO(b"missing"))
    monkeypatch.setattr(http_client.urllib.request, "urlopen", raise_http_error)
    resp = http_client.http_request("https://x")
    assert resp["status"] == 404
    assert resp["ok"] is False
    assert resp["text"] == "missing"


def test_non_http_scheme_rejected():
    with pytest.raises(ValueError):
        http_client.http_request("file:///etc/passwd")


def test_timeout_is_passed_through(monkeypatch):
    captured = {}
    monkeypatch.setattr(http_client.urllib.request, "urlopen",
                        _capture_request(captured))
    http_client.http_request("https://x", timeout=5)
    assert captured["timeout"] == 5.0


def test_facade_and_executor_wiring(monkeypatch):
    monkeypatch.setattr(http_client.urllib.request, "urlopen",
                        lambda req, timeout=None: _FakeResponse(201, '{"id": 7}'))
    assert ac.http_request is http_client.http_request
    assert "AC_http_request" in ac.executor.known_commands()
    record = ac.execute_action(
        [["AC_http_request", {"url": "https://x", "method": "POST",
                              "json_body": {"a": 1}}]])
    assert any("201" in str(value) for value in record.values())


def test_mcp_tool_registered():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_http_request" in names
