"""Round-3 regression: failing tools must return an isError result.

The tool-invocation catch tuple omitted the framework exception family
(``AutoControlException`` and its subclasses such as
``ImageNotFoundException``), ``subprocess.TimeoutExpired`` and
``sqlite3.Error``. A tool raising any of those escaped both containment
layers — over stdio the worker thread died and the client hung; over HTTP
the connection aborted. These tests drive the dispatcher directly.
"""
import json
import sqlite3
import subprocess
from typing import Any, Dict

import pytest

from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool


def _tool(name: str, exc: Exception) -> MCPTool:
    def handler():
        raise exc
    return MCPTool(
        name=name, description=name,
        input_schema={"type": "object", "properties": {}},
        handler=handler,
    )


def _call(server: MCPServer, name: str) -> Dict[str, Any]:
    raw = server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": {}},
    }))
    assert raw is not None
    return json.loads(raw)


@pytest.mark.parametrize("exc", [
    ImageNotFoundException("not on screen"),
    subprocess.TimeoutExpired(cmd="sleep", timeout=1.0),
    sqlite3.OperationalError("no such table"),
])
def test_framework_and_external_errors_become_iserror_result(exc):
    name = "boom"
    server = MCPServer(tools=[_tool(name, exc)])
    decoded = _call(server, name)
    # A contained failure is a *result* with isError, never a JSON-RPC error
    # and never an escaped exception (which would have hung the transport).
    assert "result" in decoded, decoded
    assert decoded["result"]["isError"] is True
    assert decoded["result"]["content"][0]["type"] == "text"


def test_error_response_does_not_leak_as_minus_32603():
    server = MCPServer(tools=[_tool("img", ImageNotFoundException("x"))])
    decoded = _call(server, "img")
    assert "error" not in decoded
