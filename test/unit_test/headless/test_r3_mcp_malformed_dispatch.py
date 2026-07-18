"""Round-3 regression: one malformed message must not kill the server.

``params`` was never validated to be an object (a list ``params`` reached
handlers that call ``params.get`` and raised ``AttributeError``), and an
inbound response with a non-hashable ``id`` raised ``TypeError`` when used
as a dict key. Neither was guarded, and the stdio read loop had no net, so a
single bad line terminated the whole server. These tests drive the
dispatcher and the stdio loop directly.
"""
import io
import json

from je_auto_control.utils.mcp_server.server import MCPServer


def test_request_with_non_object_params_returns_invalid_params():
    server = MCPServer(tools=[])
    decoded = json.loads(server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": [1],
    })))
    assert decoded["error"]["code"] == -32602


def test_notification_with_non_object_params_does_not_raise():
    server = MCPServer(tools=[])
    # A list-typed params on a notification path previously reached
    # _cancel_active_call([...]).get -> AttributeError, uncaught in handle_line.
    result = server.handle_line(json.dumps({
        "jsonrpc": "2.0", "method": "notifications/cancelled", "params": [1],
    }))
    assert result is None


def test_inbound_response_with_non_hashable_id_is_dropped():
    server = MCPServer(tools=[])
    # {"id": [1], "result": {}} is treated as a reply to a server request;
    # the id is a dict key, so a list id raised TypeError before the guard.
    result = server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": [1], "result": {},
    }))
    assert result is None


def test_stdio_loop_survives_a_malformed_line():
    server = MCPServer(tools=[])
    lines = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": [1], "result": {}}),  # bad id
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
    ]) + "\n"
    out = io.StringIO()
    server.serve_stdio(stdin=io.StringIO(lines), stdout=out)
    responses = [json.loads(line) for line in out.getvalue().splitlines()
                 if line.strip()]
    # The ping after the malformed line proves the loop kept running.
    ids = [msg.get("id") for msg in responses]
    assert 2 in ids
