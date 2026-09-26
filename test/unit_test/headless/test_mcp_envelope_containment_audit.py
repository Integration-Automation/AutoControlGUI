"""Every tools/call is answered, plain POSTs answer inline, audit failures, root arrays, JSON-RPC envelopes.

A tool raising ``re.PatternError`` (or any error outside a fixed list) left
the call unanswered; a plain POST to a concurrent server was acknowledged 202
with no body; an unwritable audit log turned a tool that ran into an internal
error; the JSON document tools refused root arrays; ``"id": null`` was taken
for a notification and malformed envelopes got the wrong error codes.
"""
import json
import re
import urllib.request

import pytest
from defusedxml.ElementTree import ParseError

from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.mcp_server.tools._base import MCPTool, schema

_TEST_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS out of scope


def _call(server, name, arguments=None, msg_id=1):
    reply = server.handle_line(json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
                                           "params": {"name": name, "arguments": arguments or {}}}))
    return json.loads(reply)


def _raising(error):
    def handler():
        raise error
    return MCPTool(name="boom", description="raises", input_schema=schema({}), handler=handler)


class _PluginError(Exception):
    """An error type no containment list knows."""


@pytest.mark.parametrize("error", [re.error("missing )"), ParseError("bad xml"), _PluginError("custom")])
def test_a_tool_error_of_any_type_is_answered_with_is_error(error):
    reply = _call(MCPServer(tools=[_raising(error)]), "boom")
    assert reply["result"]["isError"] is True


def test_a_bad_regex_is_a_value_error_in_the_data_tools():
    from je_auto_control.utils.data_quality.data_quality import extract_fields, validate_rows
    with pytest.raises(ValueError, match="invalid regex"):
        validate_rows([{"a": "x"}], {"a": {"regex": "("}})
    with pytest.raises(ValueError, match="invalid regex"):
        extract_fields("text", patterns={"p": "("})


def test_a_plain_post_to_a_concurrent_server_answers_in_its_body():
    from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
    tool = MCPTool(name="echo", description="echo", input_schema=schema({}), handler=lambda: "hi")
    http = HttpMCPServer(mcp=MCPServer(tools=[tool], concurrent_tools=True), host="127.0.0.1", port=0)
    http.start()
    try:
        host, port = http.address
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "echo", "arguments": {}}}).encode("utf-8")
        request = urllib.request.Request(f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}", data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310
            status, text = response.status, response.read().decode("utf-8")
    finally:
        http.stop(timeout=1.0)
    assert status == 200 and json.loads(text)["result"]["isError"] is False


def test_an_unwritable_audit_log_does_not_fail_a_tool_that_ran(tmp_path):
    ran = []
    tool = MCPTool(name="act", description="acts", input_schema=schema({}), handler=lambda: ran.append(1) or "done")
    server = MCPServer(tools=[tool], audit_logger=AuditLogger(str(tmp_path / "missing" / "audit.jsonl")))
    reply = _call(server, "act")
    assert ran == [1] and reply["result"]["isError"] is False
    assert "audit.jsonl" not in json.dumps(reply)


@pytest.mark.parametrize("name, arguments", [
    ("ac_json_query", {"data": [{"id": 1}, {"id": 2}], "path": "$[1].id"}),
    ("ac_resolve_pointer", {"doc": [10, 20], "pointer": "/1"}),
    ("ac_diff_json", {"actual": [1, 2], "expected": [1, 3]}),
])
def test_json_document_tools_take_a_root_array(name, arguments):
    tools = {tool.name: tool for tool in build_default_tool_registry(aliases=False)}
    reply = _call(MCPServer(tools=[tools[name]]), name, arguments)
    assert reply["result"]["isError"] is False, reply


@pytest.mark.parametrize("message, code, reply_id", [
    ({"jsonrpc": "2.0", "id": 1}, -32600, 1),
    ({"jsonrpc": "2.0", "id": 1, "method": ["ping"]}, -32600, 1),
    ({"jsonrpc": "2.0", "id": [1], "method": "ping"}, -32600, None),
    ({"jsonrpc": "2.0", "id": {"a": 1}, "method": "ping"}, -32600, None),
    ({"jsonrpc": "2.0", "id": True, "method": "ping"}, -32600, None),
    ({"jsonrpc": "1.0", "id": 1, "method": "ping"}, -32600, 1),
    ({"id": 1, "method": "ping"}, -32600, 1),
])
def test_malformed_envelopes_are_invalid_requests(message, code, reply_id):
    reply = json.loads(MCPServer(tools=[]).handle_line(json.dumps(message)))
    assert reply["error"]["code"] == code and reply["id"] == reply_id


def test_a_null_id_is_a_request_and_a_missing_id_a_notification():
    server = MCPServer(tools=[])
    assert json.loads(server.handle_line(json.dumps({"jsonrpc": "2.0", "id": None, "method": "ping"}))) == {
        "jsonrpc": "2.0", "id": None, "result": {}}
    assert server.handle_line(json.dumps({"jsonrpc": "2.0", "method": "ping"})) is None
    assert server.handle_line(json.dumps({"jsonrpc": "2.0", "id": [1], "result": {}})) is None
