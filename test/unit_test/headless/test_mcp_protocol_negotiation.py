"""MCP lifecycle and transport rules the server follows (loopback only).

Version negotiation answers with a version the server implements; the
server's capabilities hold only server capabilities; an unsupported
``MCP-Protocol-Version`` header is a 400; sampling is only asked of a client
that declared it.
"""
import json
import time
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.mcp_server._protocol import (
    PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS,
)
from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
from je_auto_control.utils.mcp_server.server import MCPServer

_TEST_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS out of scope


def _initialize(server, version):
    params = {} if version is None else {"protocolVersion": version}
    line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params})
    return json.loads(server.handle_line(line))["result"]


@pytest.mark.parametrize("requested", SUPPORTED_PROTOCOL_VERSIONS)
def test_a_supported_version_is_agreed(requested):
    assert _initialize(MCPServer(tools=[]), requested)["protocolVersion"] == requested


@pytest.mark.parametrize("requested", ["2026-07-28", "2099-01-01", "", None, 42])
def test_any_other_version_gets_the_servers_newest(requested):
    assert _initialize(MCPServer(tools=[]), requested)["protocolVersion"] == PROTOCOL_VERSION


def test_server_capabilities_are_server_capabilities():
    result = _initialize(MCPServer(tools=[]), PROTOCOL_VERSION)
    assert set(result["capabilities"]) <= {"tools", "resources", "prompts", "logging",
                                           "completions", "experimental"}


def test_sampling_is_refused_at_once_without_the_client_capability():
    server = MCPServer(tools=[])
    server.set_writer(lambda _line: None)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="sampling capability"):
        server.request_sampling([{"role": "user", "content": {"type": "text", "text": "hi"}}],
                                timeout=30.0)
    assert time.monotonic() - started < 5


@pytest.fixture()
def http_server():
    server = HttpMCPServer(mcp=MCPServer(tools=[]), host="127.0.0.1", port=0)
    server.start()
    yield server
    server.stop(timeout=1.0)


def _post(server, headers):
    host, port = server.address
    data = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}).encode("utf-8")
    request = urllib.request.Request(
        f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}", data=data,
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:  # nosec B310  # reason: loopback test server
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_an_unsupported_protocol_version_header_is_a_400(http_server):
    assert _post(http_server, {"MCP-Protocol-Version": "2099-01-01"}) == 400
    assert _post(http_server, {"MCP-Protocol-Version": PROTOCOL_VERSION}) == 200
    assert _post(http_server, {}) == 200
