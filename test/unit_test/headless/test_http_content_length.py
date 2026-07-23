"""A malformed Content-Length must be answered, not crash the handler thread.

``http.server`` does not validate header values, so a client can send
``Content-Length: abc``. Every server here parsed it with a bare ``int(...)``,
which raised inside the handler thread: the thread died and the socket closed
with no response, so the client saw a connection reset rather than the 400 each
server already knew how to send.
"""
import socket

import pytest

from je_auto_control.utils.http_headers import (
    INVALID_CONTENT_LENGTH, parse_content_length,
)


def _status_line(port: int, path: str) -> bytes:
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    try:
        sock.sendall(
            f"POST {path} HTTP/1.1\r\nHost: x\r\n"
            "Content-Length: abc\r\nContent-Type: application/json\r\n\r\n"
            .encode()
        )
        try:
            data = sock.recv(200)
        except OSError as error:            # connection reset == thread died
            pytest.fail(f"no response, socket reset: {error}")
        assert data, "handler thread died: server sent nothing"
        return data.split(b"\r\n")[0]
    finally:
        sock.close()


# --- the shared parser -----------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("123", 123),
    ("0", 0),
    ("", 0),
    (None, 0),
    ("abc", INVALID_CONTENT_LENGTH),
    ("1.5", INVALID_CONTENT_LENGTH),
    ("-5", INVALID_CONTENT_LENGTH),
    ("  7  ", 7),
])
def test_parse_content_length_never_raises(raw, expected):
    headers = {} if raw is None else {"Content-Length": raw}
    assert parse_content_length(headers) == expected


# --- each server end to end ------------------------------------------------

def test_rest_server_answers_400(monkeypatch):
    from je_auto_control.utils.rest_api.rest_server import start_rest_api_server
    server = start_rest_api_server(host="127.0.0.1", port=0, token=None)
    try:
        assert b"400" in _status_line(server.address[1], "/execute")
    finally:
        server.stop()


def test_mcp_http_server_answers_400():
    from je_auto_control.utils.mcp_server.http_transport import (
        start_mcp_http_server,
    )
    server = start_mcp_http_server(host="127.0.0.1", port=0)
    try:
        assert b"400" in _status_line(server.address[1], "/mcp")
    finally:
        server.stop()


def test_webhook_server_answers_400(tmp_path):
    from je_auto_control.utils.triggers.webhook_server import (
        WebhookTriggerServer,
    )
    script = tmp_path / "s.json"
    script.write_text('[["AC_set_var", {"name": "a", "value": 1}]]',
                      encoding="utf-8")
    server = WebhookTriggerServer(executor=lambda actions, variables: None)
    _host, port = server.start(host="127.0.0.1", port=0)
    try:
        server.add(path="/hook", script_path=str(script), methods=["POST"])
        assert b"400" in _status_line(port, "/hook")
    finally:
        server.stop()
