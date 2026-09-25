"""The server speaks MCP 2026-07-28, the stateless revision, beside the older ones.

A request whose ``_meta`` names the protocol version is served from that
metadata alone: ``server/discover``, ``resultType`` and caching hints on every
result, the reserved error codes, the removed methods, per-request
capabilities, and destructive-tool confirmation by multi round-trip instead
of a server-initiated ``elicitation/create``. ``initialize`` still selects the
handshake era. Over HTTP that revision's header rules and status codes apply
and no session is kept. ``subscriptions/listen`` delivers only the change
notifications asked for, tagged with its id, over stdio and over HTTP. No
network beyond loopback.
"""
import base64
import http.client
import io
import json
import logging
import time
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server._http_stateless import decode_header_value
from je_auto_control.utils.mcp_server._input_required import RequestStateSigner
from je_auto_control.utils.mcp_server._protocol import SUPPORTED_PROTOCOL_VERSIONS
from je_auto_control.utils.mcp_server._stateless import (
    META_SERVER_INFO, STATELESS_PROTOCOL_VERSION,
)
from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
from je_auto_control.utils.mcp_server.log_bridge import MCPLogBridge
from je_auto_control.utils.mcp_server.resources import ResourceProvider
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
    assert result["capabilities"] == {"tools": {"listChanged": True},
                                      "resources": {"subscribe": True}, "prompts": {}}
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


# --- Streamable HTTP ---------------------------------------------------------

_TEST_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS out of scope


@pytest.fixture()
def http_server(monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE", "1")
    server = HttpMCPServer(mcp=MCPServer(tools=[_tool(), _tool(name="read", annotations=READ_ONLY)]),
                           host="127.0.0.1", port=0)
    server.start()
    yield server
    server.stop(timeout=1.0)


def _headers_for(method, name=None, version=STATELESS_PROTOCOL_VERSION):
    headers = {"MCP-Protocol-Version": version, "Mcp-Method": method}
    if name is not None:
        headers["Mcp-Name"] = name
    return headers


def _http(server, body, headers, http_method="POST"):
    host, port = server.address
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{_TEST_SCHEME}://{host}:{port}{DEFAULT_PATH}", data=data, method=http_method,
        headers={"Content-Type": "application/json", "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310  # reason: loopback test server
            return response.status, json.loads(response.read() or b"null"), dict(response.headers)
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, (json.loads(raw) if raw else None), dict(error.headers)


def _request(method, params=None, capabilities=None, msg_id=1):
    return {"jsonrpc": "2.0", "id": msg_id, "method": method,
            "params": {**(params or {}), "_meta": _meta(capabilities)}}


def test_a_stateless_http_request_is_served_without_a_session(http_server):
    status, body, headers = _http(http_server, _request("tools/list"), _headers_for("tools/list"))
    assert status == 200 and body["result"]["resultType"] == "complete"
    assert "Mcp-Session-Id" not in headers
    # An unknown session id is ignored rather than a 404: there are no sessions.
    status, body, _ = _http(http_server, _request("server/discover"),
                            {**_headers_for("server/discover"), "Mcp-Session-Id": "nope"})
    assert status == 200 and STATELESS_PROTOCOL_VERSION in body["result"]["supportedVersions"]


@pytest.mark.parametrize("headers, detail", [
    ({"MCP-Protocol-Version": STATELESS_PROTOCOL_VERSION}, "Mcp-Method"),
    (_headers_for("tools/call"), "Mcp-Method"),
    (_headers_for("tools/list", version="2025-11-25"), "MCP-Protocol-Version"),
    ({"Mcp-Method": "tools/list"}, "MCP-Protocol-Version"),
])
def test_headers_that_disagree_with_the_body_are_a_header_mismatch(http_server, headers, detail):
    status, body, _ = _http(http_server, _request("tools/list"), headers)
    assert status == 400 and body["error"]["code"] == -32020 and detail in body["error"]["message"]


def test_mcp_name_mirrors_the_tool_name(http_server):
    call = _request("tools/call", {"name": "read", "arguments": {"x": 1}})
    assert _http(http_server, call, _headers_for("tools/call"))[1]["error"]["code"] == -32020
    assert _http(http_server, call, _headers_for("tools/call", "act"))[1]["error"]["code"] == -32020
    status, body, _ = _http(http_server, call, _headers_for("tools/call", "read"))
    assert status == 200 and body["result"]["isError"] is False
    encoded = "=?base64?" + base64.b64encode(b"read").decode() + "?="
    assert _http(http_server, call, _headers_for("tools/call", encoded))[0] == 200


def test_version_and_metadata_errors_are_400_and_unknown_methods_404(http_server):
    status, body, _ = _http(http_server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                            _headers_for("tools/list"))
    assert status == 400 and body["error"]["code"] == -32602
    status, body, _ = _http(http_server, _request("ping"), _headers_for("ping"))
    assert status == 404 and body["error"]["code"] == -32601
    status, body, _ = _http(http_server, _request("tools/list"),
                            _headers_for("tools/list", version="2099-01-01"))
    assert status == 400 and body["error"]["code"] == -32022 and body["id"] == 1
    assert STATELESS_PROTOCOL_VERSION in body["error"]["data"]["supported"]


def test_confirmation_over_http_is_a_multi_round_trip(http_server):
    call = _request("tools/call", {"name": "act", "arguments": {"x": 2}}, {"elicitation": {}})
    status, body, _ = _http(http_server, call, _headers_for("tools/call", "act"))
    assert status == 200 and body["result"]["resultType"] == "input_required"
    retry = _request("tools/call", {"name": "act", "arguments": {"x": 2},
                                    "requestState": body["result"]["requestState"],
                                    "inputResponses": {"confirm": {"action": "accept"}}},
                     {"elicitation": {}}, msg_id=2)
    status, body, _ = _http(http_server, retry, _headers_for("tools/call", "act"))
    assert status == 200 and body["result"]["isError"] is False
    bare = _request("tools/call", {"name": "act", "arguments": {"x": 2}})
    status, body, _ = _http(http_server, bare, _headers_for("tools/call", "act"))
    assert status == 400 and body["error"]["code"] == -32021


def test_get_and_delete_are_not_part_of_the_stateless_revision(http_server):
    headers = {"MCP-Protocol-Version": STATELESS_PROTOCOL_VERSION, "Accept": "text/event-stream"}
    assert _http(http_server, None, headers, http_method="GET")[0] == 405
    assert _http(http_server, None, headers, http_method="DELETE")[0] == 405


def test_the_handshake_era_still_gets_a_session(http_server):
    status, body, headers = _http(http_server, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                                "params": {"protocolVersion": "2025-11-25"}}, {})
    assert status == 200 and body["result"]["protocolVersion"] == "2025-11-25"
    assert headers.get("Mcp-Session-Id")


@pytest.mark.parametrize("value, decoded", [
    ("plain", "plain"),
    ("=?base64?SGVsbG8sIOS4lueVjA==?=", "Hello, " + chr(0x4E16) + chr(0x754C)),
    ("=?base64?!!?=", None),
    ("caf" + chr(0xE9), None),
    ("line" + chr(10) + "break", None),
])
def test_header_values_decode_as_the_spec_says(value, decoded):
    assert decode_header_value(value) == decoded


# --- subscriptions/listen ------------------------------------------------------

class _Updates(ResourceProvider):
    """A resource provider whose one resource updates when the test says so."""

    URI = "test://live"

    def __init__(self):
        self.callbacks = {}
        self.unsubscribed = []

    def list(self):
        return []

    def read(self, uri):
        return None

    def subscribe(self, uri, on_update):
        if uri != self.URI:
            return None
        handle = len(self.callbacks) + len(self.unsubscribed) + 1
        self.callbacks[handle] = on_update
        return handle

    def unsubscribe(self, uri, handle):
        self.unsubscribed.append(handle)
        self.callbacks.pop(handle, None)

    def update(self):
        for callback in list(self.callbacks.values()):
            callback()


def _listening(filter_, msg_id=7):
    provider = _Updates()
    server = MCPServer(tools=[], resource_provider=provider)
    written = []
    server.set_writer(lambda line: written.append(json.loads(line)))
    unsolicited = []
    server.set_notifier(lambda method, params: unsolicited.append(method))
    reply = server.handle_line(json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": "subscriptions/listen",
                                           "params": {"_meta": _meta(), "notifications": filter_}}))
    return server, provider, written, unsolicited, reply


def test_listen_acknowledges_what_it_will_send_and_answers_nothing_yet():
    _, _, written, _, reply = _listening({
        "toolsListChanged": True, "promptsListChanged": True, "resourcesListChanged": True,
        "resourceSubscriptions": [_Updates.URI, "test://nothing", _Updates.URI]})
    assert reply is None
    assert written == [{"jsonrpc": "2.0", "method": "notifications/subscriptions/acknowledged", "params": {
        "_meta": {"io.modelcontextprotocol/subscriptionId": 7},
        "notifications": {"toolsListChanged": True, "resourceSubscriptions": [_Updates.URI]}}}]


def test_listen_delivers_only_what_was_asked_for_tagged_with_its_id():
    server, provider, written, unsolicited, _ = _listening({"resourceSubscriptions": [_Updates.URI]})
    server.register_tool(_tool(name="late"))
    provider.update()
    assert [message["method"] for message in written] == [
        "notifications/subscriptions/acknowledged", "notifications/resources/updated"]
    assert written[1]["params"] == {"uri": _Updates.URI,
                                    "_meta": {"io.modelcontextprotocol/subscriptionId": 7}}
    assert unsolicited == []
    tools_only, _, tool_written, _, _ = _listening({"toolsListChanged": True}, msg_id="s")
    tools_only.register_tool(_tool(name="late"))
    assert tool_written[1] == {"jsonrpc": "2.0", "method": "notifications/tools/list_changed",
                               "params": {"_meta": {"io.modelcontextprotocol/subscriptionId": "s"}}}


def test_a_cancelled_subscription_stops_silently_and_releases_its_resources():
    server, provider, written, _, _ = _listening({"toolsListChanged": True,
                                                  "resourceSubscriptions": [_Updates.URI]})
    server.handle_line(json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                   "params": {"requestId": 7}}))
    assert provider.unsubscribed == [1] and provider.callbacks == {}
    server.register_tool(_tool(name="late"))
    assert len(written) == 1 and server.subscription(None, 7) is None


def test_the_server_ending_a_subscription_answers_the_listen_request():
    server, provider, written, _, _ = _listening({"resourceSubscriptions": [_Updates.URI]})
    closed = server.subscription(None, 7)
    server.end_subscriptions(stdio=True)
    assert written[-1] == {"jsonrpc": "2.0", "id": 7, "result": {
        "resultType": "complete", "_meta": {"io.modelcontextprotocol/subscriptionId": 7}}}
    assert closed.is_set() and provider.unsubscribed == [1]


@pytest.mark.parametrize("filter_, code", [
    (None, -32602), ({"toolsListChanged": "yes"}, -32602),
    ({"resourceSubscriptions": "test://live"}, -32602), ({"resourceSubscriptions": [1]}, -32602),
])
def test_a_malformed_filter_is_invalid_params(filter_, code):
    _, _, written, _, reply = _listening(filter_)
    assert json.loads(reply)["error"]["code"] == code and written == []


def test_one_id_listens_once():
    server, _, _, _, _ = _listening({"toolsListChanged": True})
    again = server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 7, "method": "subscriptions/listen",
                                           "params": {"_meta": _meta(), "notifications": {}}}))
    assert json.loads(again)["error"]["code"] == -32600


def test_listen_over_stdio_is_answered_when_the_loop_ends():
    server = MCPServer(tools=[], resource_provider=_Updates())
    request = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "subscriptions/listen",
                          "params": {"_meta": _meta(), "notifications": {"toolsListChanged": True}}})
    out = io.StringIO()
    server.serve_stdio(stdin=io.StringIO(request + "\n"), stdout=out)
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [line.get("method", "result") for line in lines] == [
        "notifications/subscriptions/acknowledged", "result"]
    assert lines[1]["id"] == 3 and lines[1]["result"]["resultType"] == "complete"


def _open_listen(server, filter_):
    host, port = server.address
    connection = http.client.HTTPConnection(host, port, timeout=5)
    body = json.dumps(_request("subscriptions/listen", {"notifications": filter_}, msg_id=11))
    connection.request("POST", DEFAULT_PATH, body=body, headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        **_headers_for("subscriptions/listen")})
    return connection, connection.getresponse()


def _next_event(response):
    while True:
        line = response.fp.readline()
        if not line:
            return None
        if line.startswith(b"data: "):
            return json.loads(line[len(b"data: "):])


def test_listen_over_http_streams_until_the_server_stops():
    server = HttpMCPServer(mcp=MCPServer(tools=[]), host="127.0.0.1", port=0)
    server.start()
    try:
        connection, response = _open_listen(server, {"toolsListChanged": True})
        assert response.status == 200 and response.getheader("X-Accel-Buffering") == "no"
        assert "Mcp-Session-Id" not in dict(response.getheaders())
        assert _next_event(response)["params"]["notifications"] == {"toolsListChanged": True}
        server.mcp.register_tool(_tool(name="late"))
        changed = _next_event(response)
        assert changed["method"] == "notifications/tools/list_changed"
        assert changed["params"]["_meta"] == {"io.modelcontextprotocol/subscriptionId": 11}
    finally:
        server.stop(timeout=2.0)
    assert _next_event(response) == {"jsonrpc": "2.0", "id": 11, "result": {
        "resultType": "complete", "_meta": {"io.modelcontextprotocol/subscriptionId": 11}}}
    assert _next_event(response) is None
    connection.close()


def test_listen_over_http_ends_when_the_client_goes_away():
    server = HttpMCPServer(mcp=MCPServer(tools=[]), host="127.0.0.1", port=0)
    server.start()
    try:
        connection, response = _open_listen(server, {"toolsListChanged": True})
        _next_event(response)
        response.close()  # the connection handed its socket to the response
        connection.close()
        deadline = time.monotonic() + 10
        while server.mcp._listeners and time.monotonic() < deadline:  # noqa: SLF001  # reason: the registry is the observable
            server.mcp.register_tool(_tool(name=f"late{time.monotonic_ns()}"))
            time.sleep(0.05)
        assert not server.mcp._listeners  # noqa: SLF001
    finally:
        server.stop(timeout=2.0)


def test_listen_over_http_needs_an_event_stream(http_server):
    body = _request("subscriptions/listen", {"notifications": {"toolsListChanged": True}})
    status, reply, _ = _http(http_server, body, _headers_for("subscriptions/listen"))
    assert status == 406 and reply["error"]["code"] == -32600
