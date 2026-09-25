"""The server speaks MCP 2025-11-25 (no network except loopback).

It negotiates the revision and is newest, describes itself in ``serverInfo``
only to clients of that revision, reports input validation errors as tool
execution errors (SEP-1303), and every registered tool follows the naming
guidance (SEP-986) and reads the same under JSON Schema 2020-12 (SEP-1613).
"""
import json
import re
import urllib.request

import pytest

from je_auto_control.utils.mcp_server._protocol import (
    PROTOCOL_VERSION, SERVER_DESCRIPTION, SUPPORTED_PROTOCOL_VERSIONS,
)
from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, build_default_tool_registry

_TEST_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS out of scope
#: Keywords that mean something else, or nothing, under 2020-12.
_DRAFT_07_ONLY = {"definitions", "dependencies", "additionalItems"}


def _send(server, method, params, msg_id=1):
    return json.loads(server.handle_line(json.dumps(
        {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})))


def test_2025_11_25_is_the_newest_and_is_agreed():
    assert PROTOCOL_VERSION == "2025-11-25" == SUPPORTED_PROTOCOL_VERSIONS[0]
    result = _send(MCPServer(tools=[]), "initialize", {"protocolVersion": "2025-11-25"})["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert result["serverInfo"]["description"] == SERVER_DESCRIPTION


def test_older_clients_get_the_serverinfo_their_revision_defines():
    result = _send(MCPServer(tools=[]), "initialize", {"protocolVersion": "2025-06-18"})["result"]
    assert set(result["serverInfo"]) == {"name", "version"}


def test_an_input_validation_error_is_a_tool_execution_error():
    tool = MCPTool(name="needs_x", description="d",
                   input_schema={"type": "object", "properties": {"x": {"type": "integer"}},
                                 "required": ["x"]},
                   handler=lambda x: x)
    server = MCPServer(tools=[tool])
    reply = _send(server, "tools/call", {"name": "needs_x", "arguments": {"x": "nine"}})
    assert "error" not in reply and reply["result"]["isError"] is True
    assert "expected integer" in reply["result"]["content"][0]["text"]
    # A request the protocol cannot read, and an unknown tool, stay protocol errors.
    assert _send(server, "tools/call", {"name": "no_such_tool"})["error"]["code"] == -32602
    assert _send(server, "tools/call", {"name": 7})["error"]["code"] == -32602


def _schema_nodes(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            if key != "properties":
                yield from _schema_nodes(value, f"{path}/{key}")
            elif isinstance(value, dict):
                for name, sub in value.items():
                    yield from _schema_nodes(sub, f"{path}/properties/{name}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _schema_nodes(item, f"{path}/{index}")


def test_every_tool_follows_the_2025_11_25_guidance():
    tools = build_default_tool_registry()
    names = [tool.name for tool in tools]
    assert len(names) == len(set(names))
    assert [n for n in names if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,128}", n)] == []
    stale = []
    for tool in tools:
        assert isinstance(tool.input_schema, dict) and tool.input_schema.get("type") == "object", tool.name
        for schema in filter(None, (tool.input_schema, tool.output_schema)):
            stale += [(tool.name, path, key) for path, key, value in _schema_nodes(schema)
                      if key in _DRAFT_07_ONLY or (key == "items" and isinstance(value, list))]
    assert stale == []


@pytest.fixture()
def http_server():
    server = HttpMCPServer(mcp=MCPServer(tools=[]), host="127.0.0.1", port=0)
    server.start()
    yield server
    server.stop(timeout=1.0)


def test_http_accepts_the_2025_11_25_header(http_server):
    host, port = http_server.address
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
    request = urllib.request.Request(
        f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}", data=body, method="POST",
        headers={"Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25"})
    with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310  # reason: loopback test server
        assert response.status == 200
