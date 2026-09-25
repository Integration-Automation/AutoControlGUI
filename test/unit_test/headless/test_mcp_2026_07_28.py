"""The server speaks MCP 2026-07-28, the stateless revision, beside the older ones.

A request whose ``_meta`` names the protocol version is served from that
metadata alone: ``server/discover``, ``resultType`` and caching hints on every
result, the reserved error codes, the removed methods, per-request
capabilities, and destructive-tool confirmation by multi round-trip instead
of a server-initiated ``elicitation/create``. ``initialize`` still selects the
handshake era. No network.
"""
import json
import logging

import pytest

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server._input_required import RequestStateSigner
from je_auto_control.utils.mcp_server._protocol import SUPPORTED_PROTOCOL_VERSIONS
from je_auto_control.utils.mcp_server._stateless import (
    META_SERVER_INFO, STATELESS_PROTOCOL_VERSION,
)
from je_auto_control.utils.mcp_server.log_bridge import MCPLogBridge
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool
from je_auto_control.utils.mcp_server.tools._base import DESTRUCTIVE, READ_ONLY


def _meta(capabilities=None, **extra):
    meta = {"io.modelcontextprotocol/protocolVersion": STATELESS_PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientInfo": {"name": "t", "version": "1"},
            "io.modelcontextprotocol/clientCapabilities": capabilities or {}}
    meta.update(extra)
    return meta


def _send(server, method, params=None, msg_id=1, **meta_extra):
    params = dict(params or {})
    if "_meta" not in params:
        params["_meta"] = _meta(**meta_extra)
    return json.loads(server.handle_line(json.dumps(
        {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})))


def _tool(name="act", annotations=DESTRUCTIVE, calls=None):
    def handler(x=0):
        if calls is not None:
            calls.append(x)
        return {"ran": x}
    return MCPTool(name=name, description="d",
                   input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
                   handler=handler, annotations=annotations)


def test_discover_names_every_version_and_the_servers_identity():
    result = _send(MCPServer(tools=[]), "server/discover")["result"]
    assert result["resultType"] == "complete"
    assert result["supportedVersions"] == [STATELESS_PROTOCOL_VERSION, *SUPPORTED_PROTOCOL_VERSIONS]
    assert set(result["capabilities"]) == {"tools", "resources", "prompts"}
    assert result["_meta"][META_SERVER_INFO]["name"] == "je_auto_control"
    assert result["ttlMs"] > 0 and result["cacheScope"] == "private"


def test_discover_without_the_per_request_fields_is_invalid_params():
    server = MCPServer(tools=[])
    line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}})
    assert json.loads(server.handle_line(line))["error"]["code"] == -32602


def test_an_unsupported_version_lists_the_supported_ones():
    error = _send(MCPServer(tools=[]), "tools/list", {"_meta": {
        "io.modelcontextprotocol/protocolVersion": "1900-01-01",
        "io.modelcontextprotocol/clientCapabilities": {}}})["error"]
    assert error["code"] == -32022
    assert error["data"] == {"supported": [STATELESS_PROTOCOL_VERSION, *SUPPORTED_PROTOCOL_VERSIONS],
                             "requested": "1900-01-01"}


@pytest.mark.parametrize("meta", [
    {"io.modelcontextprotocol/protocolVersion": STATELESS_PROTOCOL_VERSION},
    {"io.modelcontextprotocol/protocolVersion": STATELESS_PROTOCOL_VERSION,
     "io.modelcontextprotocol/clientCapabilities": []},
    _meta(**{"io.modelcontextprotocol/logLevel": "chatty"}),
])
def test_missing_or_malformed_per_request_fields_are_invalid_params(meta):
    assert _send(MCPServer(tools=[]), "tools/list", {"_meta": meta})["error"]["code"] == -32602


@pytest.mark.parametrize("params", [{"inputResponses": []}, {"requestState": 7}])
def test_malformed_retry_fields_are_invalid_params(params):
    reply = _send(MCPServer(tools=[_tool()]), "tools/call", {"name": "act", **params, "_meta": _meta()})
    assert reply["error"]["code"] == -32602


@pytest.mark.parametrize("method", ["ping", "logging/setLevel", "resources/subscribe",
                                    "resources/unsubscribe", "no/such/method"])
def test_methods_the_revision_removed_are_not_found(method):
    assert _send(MCPServer(tools=[]), method, {"uri": "x", "level": "info"})["error"]["code"] == -32601


def test_every_result_says_it_is_complete_and_lists_carry_caching_hints():
    server = MCPServer(tools=[_tool(annotations=READ_ONLY)])
    listed = _send(server, "tools/list")["result"]
    assert listed["resultType"] == "complete" and [t["name"] for t in listed["tools"]] == ["act"]
    assert listed["ttlMs"] == 60_000 and listed["cacheScope"] == "private"
    for method in ("resources/list", "prompts/list"):
        assert _send(server, method)["result"]["cacheScope"] == "private"
    called = _send(server, "tools/call", {"name": "act", "arguments": {"x": 3}, "_meta": _meta()})["result"]
    assert called["resultType"] == "complete" and called["isError"] is False
    assert "ttlMs" not in called and called["_meta"][META_SERVER_INFO]["version"]


def test_an_unknown_resource_is_invalid_params():
    reply = _send(MCPServer(tools=[]), "resources/read", {"uri": "autocontrol://nope", "_meta": _meta()})
    assert reply["error"]["code"] == -32602


def test_initialize_still_selects_the_handshake_era():
    server = MCPServer(tools=[])
    result = _send(server, "initialize", {"protocolVersion": STATELESS_PROTOCOL_VERSION})["result"]
    assert result["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[0]
    assert "resultType" not in result
    legacy = json.loads(server.handle_line(json.dumps(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})))["result"]
    assert "resultType" not in legacy and "ttlMs" not in legacy


def test_capabilities_come_from_the_request_not_the_connection():
    server = MCPServer(tools=[])
    server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                   "params": {"capabilities": {"sampling": {}}}}))
    seen = []
    server._tools["probe"] = MCPTool(  # noqa: SLF001  # reason: a tool that reads the scope
        name="probe", description="d", input_schema={"type": "object", "properties": {}},
        handler=lambda: seen.append(dict(server._client_capabilities)) or "ok",  # noqa: SLF001
        annotations=READ_ONLY)
    _send(server, "tools/call", {"name": "probe", "_meta": _meta({"roots": {}})})
    assert seen == [{"roots": {}}]
    assert server._client_capabilities == {"sampling": {}}  # noqa: SLF001


def test_no_server_initiated_request_is_sent_in_a_stateless_request():
    server = MCPServer(tools=[])
    written = []
    server.set_writer(written.append)
    errors = []

    def asks():
        try:
            server.request_sampling([{"role": "user", "content": {"type": "text", "text": "?"}}],
                                    timeout=0.1)
        except RuntimeError as error:
            errors.append(str(error))
        return "done"
    server._tools["asks"] = MCPTool(name="asks", description="d",  # noqa: SLF001
                                    input_schema={"type": "object", "properties": {}},
                                    handler=asks, annotations=READ_ONLY)
    _send(server, "tools/call", {"name": "asks", "_meta": _meta({"sampling": {}})})
    assert written == [] and "2026-07-28" in errors[0]


# --- destructive confirmation by multi round-trip ---------------------------

@pytest.fixture()
def gated(monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE", "1")
    calls = []
    return MCPServer(tools=[_tool(calls=calls)]), calls


def _call(server, capabilities, **retry):
    params = {"name": "act", "arguments": {"x": 5}, "_meta": _meta(capabilities), **retry}
    return _send(server, "tools/call", params, msg_id=len(json.dumps(retry)))


def test_a_destructive_call_asks_for_confirmation_by_input_required(gated):
    server, calls = gated
    written = []
    server.set_writer(written.append)
    result = _call(server, {"elicitation": {}})["result"]
    assert result["resultType"] == "input_required" and "ttlMs" not in result
    question = result["inputRequests"]["confirm"]
    assert question["method"] == "elicitation/create" and question["params"]["mode"] == "form"
    assert isinstance(result["requestState"], str)
    assert calls == [] and written == []


def test_an_accepted_retry_runs_the_tool_once(gated):
    server, calls = gated
    state = _call(server, {"elicitation": {}})["result"]["requestState"]
    accepted = {"inputResponses": {"confirm": {"action": "accept"}}, "requestState": state}
    done = _call(server, {"elicitation": {}}, **accepted)["result"]
    assert done["resultType"] == "complete" and done["isError"] is False and calls == [5]
    # The same state again is a replay.
    assert _call(server, {"elicitation": {}}, **accepted)["error"]["code"] == -32602
    assert calls == [5]


@pytest.mark.parametrize("action", ["decline", "cancel"])
def test_a_declined_retry_is_a_tool_error_and_does_not_run(gated, action):
    server, calls = gated
    state = _call(server, {"elicitation": {}})["result"]["requestState"]
    result = _call(server, {"elicitation": {}}, requestState=state,
                   inputResponses={"confirm": {"action": action}})["result"]
    assert result["isError"] is True and action in result["content"][0]["text"] and calls == []


def test_a_retry_without_an_answer_is_asked_again(gated):
    server, calls = gated
    state = _call(server, {"elicitation": {}})["result"]["requestState"]
    again = _call(server, {"elicitation": {}}, requestState=state, inputResponses={})["result"]
    assert again["resultType"] == "input_required" and again["requestState"] != state
    assert calls == []


def test_a_state_for_other_arguments_is_refused(gated):
    server, calls = gated
    state = _call(server, {"elicitation": {}})["result"]["requestState"]
    params = {"name": "act", "arguments": {"x": 6}, "_meta": _meta({"elicitation": {}}),
              "requestState": state, "inputResponses": {"confirm": {"action": "accept"}}}
    assert _send(server, "tools/call", params, msg_id=9)["error"]["code"] == -32602
    assert calls == []


def test_a_client_without_elicitation_is_told_which_capability_is_missing(gated):
    server, calls = gated
    error = _call(server, {})["error"]
    assert error["code"] == -32021
    assert error["data"] == {"requiredCapabilities": {"elicitation": {}}}
    assert calls == []


def test_signed_states_expire_and_resist_tampering():
    now = [1000.0]
    signer = RequestStateSigner(ttl_s=10, clock=lambda: now[0])
    state = signer.issue("tools/call", "act", {"x": 1})
    payload, mac = state.split(".")
    assert not signer.redeem(f"{payload}x.{mac}", "tools/call", "act", {"x": 1})
    assert not signer.redeem("not-a-state", "tools/call", "act", {"x": 1})
    assert not signer.redeem(state, "tools/call", "other", {"x": 1})
    now[0] += 11
    assert not signer.redeem(state, "tools/call", "act", {"x": 1})
    other = RequestStateSigner()
    fresh = signer.issue("tools/call", "act", {"x": 1})
    now[0] += 1
    assert not other.redeem(fresh, "tools/call", "act", {"x": 1})
    assert signer.redeem(fresh, "tools/call", "act", {"x": 1})


# --- notifications only on request ------------------------------------------

def _capture_bridge(server):
    sent = []
    bridge = MCPLogBridge(notifier=lambda method, params: sent.append((method, params)))
    server._log_bridge = bridge  # noqa: SLF001  # reason: what serve_stdio attaches
    return bridge, sent


def _logging_tool():
    return MCPTool(name="talk", description="d", input_schema={"type": "object", "properties": {}},
                   handler=lambda: autocontrol_logger.warning("from the tool") or "ok",
                   annotations=READ_ONLY)


def test_log_records_follow_the_requests_log_level():
    server = MCPServer(tools=[_logging_tool()])
    bridge, sent = _capture_bridge(server)
    autocontrol_logger.addHandler(bridge)
    try:
        _send(server, "tools/call", {"name": "talk", "_meta": _meta()})
        assert sent == []
        _send(server, "tools/call", {"name": "talk", "_meta": _meta(
            **{"io.modelcontextprotocol/logLevel": "error"})})
        assert sent == []
        _send(server, "tools/call", {"name": "talk", "_meta": _meta(
            **{"io.modelcontextprotocol/logLevel": "warning"})})
        assert [method for method, _ in sent] == ["notifications/message"]
        # A stateless stdio peer gets no records from outside a request either.
        autocontrol_logger.warning("background")
        assert len(sent) == 1
    finally:
        autocontrol_logger.removeHandler(bridge)


def test_a_handshake_peer_still_gets_background_records():
    server = MCPServer(tools=[])
    bridge, sent = _capture_bridge(server)
    server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
    record = logging.LogRecord("je_auto_control", logging.WARNING, __file__, 1, "bg", None, None)
    bridge.handle(record)
    assert [method for method, _ in sent] == ["notifications/message"]


def test_list_changes_are_not_pushed_to_a_stateless_peer():
    server = MCPServer(tools=[])
    sent = []
    server.set_notifier(lambda method, params: sent.append(method))
    _send(server, "tools/list")
    server.register_tool(_tool(name="late"))
    assert sent == []
    handshake = MCPServer(tools=[])
    handshake.set_notifier(lambda method, params: sent.append(method))
    handshake.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
    handshake.register_tool(_tool(name="late"))
    assert sent == ["notifications/tools/list_changed"]
