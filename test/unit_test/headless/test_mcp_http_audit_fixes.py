"""MCP HTTP defects from the 2026-09-24 audit.

At the session cap the least recently seen session was evicted, so 128
anonymous ``initialize`` requests pushed out a session in real use;
``DELETE /anything`` ended a session although GET and POST answer 404 off
``/mcp``; and a session dropped while its ``initialize`` ran kept its
dispatcher state for the life of the process.
"""
import http.client
import json

from je_auto_control.utils.mcp_server import http_transport
from je_auto_control.utils.mcp_server.http_sessions import (
    SESSION_HEADER, HttpSession, SessionRegistry,
)
from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
from je_auto_control.utils.mcp_server.server import MCPServer

_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {},
    "clientInfo": {"name": "probe", "version": "1"}}}


def test_anonymous_initializes_do_not_evict_a_session_in_use():
    now = [0.0]
    registry = SessionRegistry(max_sessions=4, clock=lambda: now[0])
    used = registry.create()
    now[0] += 1
    registry.get(used.id)
    for _ in range(20):
        now[0] += 1
        registry.create()
    assert registry.get(used.id) is used


def test_a_used_session_is_evicted_only_when_every_session_is_in_use():
    now = [0.0]
    registry = SessionRegistry(max_sessions=2, clock=lambda: now[0])
    first, second = registry.create(), registry.create()
    for session in (first, second):
        now[0] += 1
        registry.get(session.id)
    now[0] += 1
    registry.create()
    assert registry.get(first.id) is None and registry.get(second.id) is second


def test_state_of_a_session_dropped_mid_request_is_released():
    forgotten = []
    bridge = type("Bridge", (), {"forget_connection": lambda _self, cid: forgotten.append(cid)})()
    session = HttpSession("s-1", 0.0)
    http_transport._forget_if_dropped(bridge, session)
    assert forgotten == []
    session.closed.set()
    http_transport._forget_if_dropped(bridge, session)
    assert forgotten == ["s-1"]


def test_delete_off_the_mcp_path_is_404_and_keeps_the_session():
    server = HttpMCPServer(mcp=MCPServer(tools=[]), host="127.0.0.1", port=0)
    server.start()
    try:
        connection = http.client.HTTPConnection(*server.address, timeout=10)
        connection.request("POST", DEFAULT_PATH, body=json.dumps(_INIT),
                           headers={"Content-Type": "application/json",
                                    "Accept": "application/json"})
        response = connection.getresponse()
        response.read()
        session_id = response.getheader(SESSION_HEADER)
        connection.request("DELETE", "/not-mcp", headers={SESSION_HEADER: session_id})
        deleted = connection.getresponse()
        deleted.read()
        assert deleted.status == 404
        connection.request("DELETE", DEFAULT_PATH, headers={SESSION_HEADER: session_id})
        ended = connection.getresponse()
        ended.read()
        assert ended.status == 200
        connection.close()
    finally:
        server.stop(timeout=2.0)
