"""Webhook-server defects from the 2026-09-24 audit.

A chunked request body read as empty (the script ran on nothing and the
client got 200), a lower-case ``bearer`` scheme was refused, and a
run-history failure dropped the connection without a response.
"""
import http.client
import io
import json
import types

import pytest

from je_auto_control.utils.http_headers import ChunkedBodyError, read_chunked_body
from je_auto_control.utils.run_history.history_store import HistoryStoreError
from je_auto_control.utils.triggers import webhook_server as ws


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setattr(ws, "default_history_store", types.SimpleNamespace(
        start_run=lambda *a, **k: 1, finish_run=lambda *a, **k: None))
    monkeypatch.setattr(ws, "capture_error_snapshot", lambda run_id: None)
    captured = []
    srv = ws.WebhookTriggerServer(executor=lambda actions, variables: captured.append(variables))
    script = tmp_path / "s.json"
    script.write_text('[["AC_screen_size"]]', encoding="utf-8")
    srv.add(path="/hook", script_path=str(script), token="abc123")
    host, port = srv.start("127.0.0.1", 0)
    srv.captured = captured  # type: ignore[attr-defined]
    srv.address = (host, port)  # type: ignore[attr-defined]
    yield srv
    srv.stop()


def _request(server, body, headers, encode_chunked=False):
    connection = http.client.HTTPConnection(*server.address, timeout=5)
    try:
        connection.request("POST", "/hook", body=body, headers=headers,
                           encode_chunked=encode_chunked)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_a_chunked_body_reaches_the_script(server):
    status, _ = _request(server, iter([b'{"a":', b" 1}"]),
                         {"Authorization": "Bearer abc123", "Content-Type": "application/json",
                          "Transfer-Encoding": "chunked"}, encode_chunked=True)
    assert status == 200
    assert server.captured[0]["webhook.body"] == '{"a": 1}'
    assert server.captured[0]["webhook.json"] == {"a": 1}


def test_the_bearer_scheme_is_case_insensitive(server):
    status, _ = _request(server, b"{}", {"Authorization": "bearer abc123"})
    assert status == 200
    for header in ("Basic abc123", "Bearer wrong", "Bearerabc123"):
        status, _ = _request(server, b"{}", {"Authorization": header})
        assert status == 401


def test_a_history_failure_is_answered(server, monkeypatch):
    def broken(*_args, **_kwargs):
        raise HistoryStoreError("database is locked")
    monkeypatch.setattr(ws.default_history_store, "start_run", broken)
    status, body = _request(server, b"{}", {"Authorization": "Bearer abc123"})
    assert status == 500
    assert json.loads(body)["fired"] is False


@pytest.mark.parametrize("stream, expected", [
    (b"3\r\nabc\r\n0\r\n\r\n", b"abc"),
    (b"3;ext=1\r\nabc\r\n2\r\nde\r\n0\r\nTrailer: x\r\n\r\n", b"abcde"),
    (b"0\r\n\r\n", b""),
])
def test_chunked_bodies_decode(stream, expected):
    assert read_chunked_body(io.BytesIO(stream), 100) == expected


@pytest.mark.parametrize("stream, too_large", [
    (b"zz\r\nabc\r\n0\r\n\r\n", False),
    (b"-3\r\nabc\r\n0\r\n\r\n", False),
    (b"5\r\nabc", False),
    (b"65\r\n" + b"x" * 101 + b"\r\n0\r\n\r\n", True),
])
def test_bad_or_oversized_chunked_bodies_are_refused(stream, too_large):
    with pytest.raises(ChunkedBodyError) as caught:
        read_chunked_body(io.BytesIO(stream), 100)
    assert caught.value.too_large is too_large
