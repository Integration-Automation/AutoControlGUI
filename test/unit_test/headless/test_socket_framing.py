"""The socket server reads a whole pretty-printed command (2026-09-24 audit).

It stopped at the first chunk containing a newline -- ordinary whitespace in
JSON -- so indented commands were cut short and failed to parse, and one sent
in two segments was refused after the first. No real action runs.
"""
import json
import socket
import time

import pytest

from je_auto_control.utils.socket_server import auto_control_socket_server as server_module

ACTIONS = [["AC_screen_size"], ["AC_set_var", {"name": "a", "value": "x" * 20000}]]


@pytest.fixture
def server(monkeypatch):
    received = []
    monkeypatch.setattr(server_module, "execute_action",
                        lambda actions: received.append(actions) or {"step": "done"})
    srv = server_module.start_autocontrol_socket_server("127.0.0.1", 0)
    srv.received = received  # type: ignore[attr-defined]
    yield srv
    srv.shutdown()
    srv.server_close()


def _exchange(server, *parts, pause=0.0):
    with socket.create_connection(server.server_address, timeout=10) as sock:
        for part in parts:
            sock.sendall(part)
            time.sleep(pause)
        reply = b""
        while b"Return_Data_Over_JE" not in reply:
            chunk = sock.recv(65536)
            if not chunk:
                break
            reply += chunk
    return reply.decode("utf-8")


def test_an_indented_command_is_read_whole(server):
    reply = _exchange(server, (json.dumps(ACTIONS, indent=2) + "\n").encode())
    assert server.received == [ACTIONS]
    assert "done" in reply


def test_a_command_split_at_a_newline_waits_for_the_rest(server):
    payload = json.dumps(ACTIONS, indent=2) + "\n"
    cut = payload.index("\n", 10) + 1
    _exchange(server, payload[:cut].encode(), payload[cut:].encode(), pause=0.3)
    assert server.received == [ACTIONS]


def test_a_malformed_command_is_still_answered_at_once(server):
    started = time.monotonic()
    reply = _exchange(server, b"{bad}\n")
    assert "Return_Data_Over_JE" in reply
    assert time.monotonic() - started < 5
    assert server.received == []


@pytest.mark.parametrize("data, complete", [
    (b'[["AC_screen_size"]]\n', True),
    (b'[\n  [\n', False),
    (b'{bad}\n', True),
    (b"quit_server\n", True),
])
def test_completeness(data, complete):
    assert server_module._is_complete(data) is complete
