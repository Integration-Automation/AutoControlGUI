"""Headless tests for the MCP HTTP transport."""
import json
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.mcp_server.http_transport import (
    DEFAULT_PATH, HttpMCPServer,
)
from je_auto_control.utils.mcp_server.prompts import StaticPromptProvider
from je_auto_control.utils.mcp_server.resources import ChainProvider
from je_auto_control.utils.mcp_server.server import MCPServer


_TEST_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS out of scope


@pytest.fixture()
def http_server():
    """Spin up an HttpMCPServer on an ephemeral port with empty providers."""
    mcp = MCPServer(
        tools=[],
        resource_provider=ChainProvider([]),
        prompt_provider=StaticPromptProvider([]),
    )
    server = HttpMCPServer(mcp=mcp, host="127.0.0.1", port=0)
    server.start()
    yield server
    server.stop(timeout=1.0)


def _post(server, body, path=DEFAULT_PATH):
    host, port = server.address
    url = f"{_TEST_SCHEME}://{host}:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers,
                                  method="POST")
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310
        return response.status, response.read().decode("utf-8")


def test_initialize_round_trips_over_http(http_server):
    status, body = _post(http_server, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    })
    assert status == 200
    payload = json.loads(body)
    assert payload["result"]["protocolVersion"] == "2024-11-05"
    assert payload["result"]["serverInfo"]["name"] == "je_auto_control"


def test_notification_returns_202(http_server):
    host, port = http_server.address
    url = f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}"
    data = json.dumps({
        "jsonrpc": "2.0", "method": "notifications/initialized",
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310
        assert response.status == 202
        assert response.read() == b""


def test_tools_list_via_http_uses_registered_tools():
    from je_auto_control.utils.mcp_server.tools import (
        MCPTool, build_default_tool_registry,
    )
    full_registry = build_default_tool_registry()
    server = HttpMCPServer(mcp=MCPServer(
        tools=full_registry,
        resource_provider=ChainProvider([]),
        prompt_provider=StaticPromptProvider([]),
    ), host="127.0.0.1", port=0)
    server.start()
    try:
        status, body = _post(server, {
            "jsonrpc": "2.0", "id": 1, "method": "tools/list",
        })
        assert status == 200
        payload = json.loads(body)
        names = {tool["name"] for tool in payload["result"]["tools"]}
        assert {"ac_get_mouse_position", "ac_screen_size"}.issubset(names)
        assert isinstance(full_registry[0], MCPTool)
    finally:
        server.stop(timeout=1.0)


def test_unknown_path_returns_404(http_server):
    try:
        _post(http_server, {"jsonrpc": "2.0", "id": 1,
                             "method": "ping"}, path="/elsewhere")
    except urllib.error.HTTPError as error:
        assert error.code == 404
    else:
        pytest.fail("expected 404 response")


def test_get_returns_405(http_server):
    host, port = http_server.address
    url = f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}"
    req = urllib.request.Request(url, method="GET")
    try:
        urllib.request.urlopen(req, timeout=3)  # nosec B310
    except urllib.error.HTTPError as error:
        assert error.code == 405
    else:
        pytest.fail("expected 405 response")


def test_invalid_content_length_rejected(http_server):
    host, port = http_server.address
    url = f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}"
    req = urllib.request.Request(url, data=b"", method="POST",
                                  headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=3)  # nosec B310
    except urllib.error.HTTPError as error:
        assert error.code == 400
    else:
        pytest.fail("expected 400 response")


def test_sse_streams_progress_then_final_response():
    """When Accept includes text/event-stream, progress + result both stream."""
    from je_auto_control.utils.mcp_server.tools import MCPTool

    def slow_handler(ctx):
        ctx.progress(0.0, total=1.0, message="starting")
        ctx.progress(0.5, total=1.0)
        ctx.progress(1.0, total=1.0, message="done")
        return "all done"

    tool = MCPTool(
        name="streamed", description="streamed",
        input_schema={"type": "object", "properties": {}},
        handler=slow_handler,
    )
    server = HttpMCPServer(mcp=MCPServer(
        tools=[tool], resource_provider=ChainProvider([]),
        prompt_provider=StaticPromptProvider([]),
    ), host="127.0.0.1", port=0)
    server.start()
    try:
        host, port = server.address
        url = f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}"
        body = json.dumps({
            "jsonrpc": "2.0", "id": 99, "method": "tools/call",
            "params": {"name": "streamed", "arguments": {},
                        "_meta": {"progressToken": "tok"}},
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as response:  # nosec B310
            assert response.status == 200
            assert "text/event-stream" in response.headers.get("Content-Type", "")
            stream = response.read().decode("utf-8")
        events = [chunk[len("data: "):] for chunk in stream.split("\n\n")
                   if chunk.startswith("data: ")]
        progress_events = [json.loads(line) for line in events
                            if '"notifications/progress"' in line]
        final_events = [json.loads(line) for line in events
                         if '"id": 99' in line]
        assert len(progress_events) == 3
        assert progress_events[0]["params"]["progressToken"] == "tok"
        assert len(final_events) == 1
        assert final_events[0]["result"]["isError"] is False
        assert final_events[0]["result"]["content"][0]["text"] == "all done"
    finally:
        server.stop(timeout=1.0)


def test_authentication_rejects_missing_bearer():
    server = HttpMCPServer(mcp=MCPServer(
        tools=[], resource_provider=ChainProvider([]),
        prompt_provider=StaticPromptProvider([]),
    ), host="127.0.0.1", port=0, auth_token="secret")
    server.start()
    try:
        host, port = server.address
        url = f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}"
        body = json.dumps({"jsonrpc": "2.0", "id": 1,
                            "method": "ping"}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=3)  # nosec B310
        except urllib.error.HTTPError as error:
            assert error.code == 401
        else:
            pytest.fail("expected 401 response")
    finally:
        server.stop(timeout=1.0)


def test_authentication_rejects_wrong_bearer():
    server = HttpMCPServer(mcp=MCPServer(
        tools=[], resource_provider=ChainProvider([]),
        prompt_provider=StaticPromptProvider([]),
    ), host="127.0.0.1", port=0, auth_token="secret")
    server.start()
    try:
        host, port = server.address
        url = f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}"
        body = json.dumps({"jsonrpc": "2.0", "id": 1,
                            "method": "ping"}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                      "Authorization": "Bearer wrong"},
        )
        try:
            urllib.request.urlopen(req, timeout=3)  # nosec B310
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            pytest.fail("expected 403 response")
    finally:
        server.stop(timeout=1.0)


def test_authentication_accepts_correct_bearer():
    server = HttpMCPServer(mcp=MCPServer(
        tools=[], resource_provider=ChainProvider([]),
        prompt_provider=StaticPromptProvider([]),
    ), host="127.0.0.1", port=0, auth_token="secret")
    server.start()
    try:
        host, port = server.address
        url = f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}"
        body = json.dumps({"jsonrpc": "2.0", "id": 1,
                            "method": "ping"}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                      "Authorization": "Bearer secret"},
        )
        with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
            assert payload["result"] == {}
    finally:
        server.stop(timeout=1.0)


def test_auth_token_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_TOKEN", "env-secret")
    server = HttpMCPServer(mcp=MCPServer(
        tools=[], resource_provider=ChainProvider([]),
        prompt_provider=StaticPromptProvider([]),
    ), host="127.0.0.1", port=0)
    assert server._auth_token == "env-secret"


def test_malformed_json_returns_parse_error(http_server):
    host, port = http_server.address
    url = f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}"
    body = b"{ not json"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["error"]["code"] == -32700
