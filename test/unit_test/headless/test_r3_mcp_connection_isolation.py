"""Round-3 regression: per-connection isolation of calls and capabilities.

Over HTTP each peer runs on its own thread but shared server-global state
made two clients that both use JSON-RPC id 1 clobber each other's active
call context (cross-cancel), and one client's ``initialize`` overwrote
another's advertised capabilities (breaking the destructive-confirmation
gate). ``connection_scope(connection_id=...)`` now scopes both. These tests
drive the dispatcher via connection_scope directly — no sockets needed.
"""
import json
import threading
from typing import Any, Dict, Optional

from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool


def _toolcall(name: str, msg_id: int) -> str:
    return json.dumps({
        "jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
        "params": {"name": name, "arguments": {}},
    })


def _cancel(request_id: int) -> str:
    return json.dumps({
        "jsonrpc": "2.0", "method": "notifications/cancelled",
        "params": {"requestId": request_id},
    })


def _initialize(caps: Dict[str, Any]) -> str:
    return json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"capabilities": caps, "protocolVersion": "2025-06-18"},
    })


class _Gate:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.proceed = threading.Event()
        self.saw_cancelled: Optional[bool] = None


def _make_tool(name: str, gate: _Gate) -> MCPTool:
    def handler(ctx):
        gate.started.set()
        gate.proceed.wait(timeout=3.0)
        gate.saw_cancelled = ctx.cancelled
        return "done"
    return MCPTool(
        name=name, description=name,
        input_schema={"type": "object", "properties": {}},
        handler=handler,
    )


def _run_in_scope(server: MCPServer, conn_id: str, line: str) -> None:
    with server.connection_scope(connection_id=conn_id):
        server.handle_line(line)


def test_same_msg_id_on_two_connections_do_not_clobber_or_cross_cancel():
    gate_a, gate_b = _Gate(), _Gate()
    server = MCPServer(tools=[_make_tool("a", gate_a), _make_tool("b", gate_b)])

    thread_a = threading.Thread(
        target=_run_in_scope, args=(server, "A", _toolcall("a", 1)))
    thread_b = threading.Thread(
        target=_run_in_scope, args=(server, "B", _toolcall("b", 1)))
    thread_a.start()
    thread_b.start()
    assert gate_a.started.wait(timeout=2.0)
    assert gate_b.started.wait(timeout=2.0)

    # Two in-flight calls sharing msg id 1 must occupy two distinct slots.
    with server._calls_lock:
        assert len(server._active_calls) == 2

    # Cancelling connection A's call must not touch connection B's.
    with server.connection_scope(connection_id="A"):
        server.handle_line(_cancel(1))
    gate_a.proceed.set()
    gate_b.proceed.set()
    thread_a.join(timeout=3.0)
    thread_b.join(timeout=3.0)

    assert gate_a.saw_cancelled is True
    assert gate_b.saw_cancelled is False


def test_client_capabilities_are_scoped_per_connection():
    server = MCPServer(tools=[])
    _run_in_scope(server, "A", _initialize({"elicitation": {}}))
    _run_in_scope(server, "B", _initialize({}))

    with server.connection_scope(connection_id="A"):
        assert "elicitation" in server._client_capabilities
    with server.connection_scope(connection_id="B"):
        assert "elicitation" not in server._client_capabilities


def test_forget_connection_drops_per_connection_capabilities():
    server = MCPServer(tools=[])
    _run_in_scope(server, "A", _initialize({"elicitation": {}}))
    server.forget_connection("A")
    with server.connection_scope(connection_id="A"):
        assert server._client_capabilities == {}
