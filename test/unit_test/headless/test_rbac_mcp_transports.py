"""RBAC on every way the MCP HTTP transport serves a request.

The role checks were only exercised on the plain JSON POST. The same server
also answers a POST as an SSE stream, holds a session's standing GET stream,
serves the stateless 2026-07-28 revision, keeps ``subscriptions/listen`` open
and can listen over TLS -- each a separate code path that has to authenticate
the caller and run the tool inside the caller's scope.

Loopback only, fake tools only: nothing touches the mouse, keyboard or screen.
"""
import datetime
import http.client
import ipaddress
import json
import ssl
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.mcp_server._stateless import STATELESS_PROTOCOL_VERSION
from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool
from je_auto_control.utils.mcp_server.tools._base import DESTRUCTIVE, READ_ONLY, schema
from je_auto_control.utils.rbac import (
    USERS_ENV, Capability, Role, UserStore, current_authorization,
)

_SSE = "application/json, text/event-stream"
_ALL = ["peek", "poke", "ac_load_plugins"]
_VISIBLE = {Role.VIEWER: _ALL[:1], Role.OPERATOR: _ALL[:2], Role.ADMIN: _ALL}


@pytest.fixture(autouse=True)
def _no_ambient_rbac(monkeypatch):
    monkeypatch.delenv(USERS_ENV, raising=False)
    monkeypatch.delenv("JE_AUTOCONTROL_MCP_TOKEN", raising=False)


@pytest.fixture()
def users(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.tokens = {
        role: store.add_user(user_id=f"{role}-user", display_name=role, role=role)
        for role in Role.all()
    }
    return store


@pytest.fixture()
def serve(tmp_path, users):
    """Start RBAC servers over three fake tools; ``calls`` records who ran what."""
    calls = []

    def tool(name, annotations):
        def handler(**_arguments):
            caller = current_authorization()
            calls.append((name, None if caller is None else caller.user_id))
            return {"ran": name}
        return MCPTool(name=name, description=name, annotations=annotations, handler=handler,
                       input_schema=schema({"actions": {"type": "array"}}))

    audit_path = tmp_path / "mcp_audit.jsonl"
    started = []

    def start(**kwargs):
        tools = [tool("peek", READ_ONLY), tool("poke", DESTRUCTIVE),
                 tool("ac_load_plugins", DESTRUCTIVE)]
        server = HttpMCPServer(
            mcp=MCPServer(tools=tools, audit_logger=AuditLogger(path=str(audit_path))),
            host="127.0.0.1", port=0, user_store=users, **kwargs)
        server.start()
        server.calls = calls
        server.audit_path = audit_path
        started.append(server)
        return server

    yield start
    for server in started:
        server.stop(timeout=2.0)


def _connection(server, context=None):
    host, port = server.address
    if context is not None:
        return http.client.HTTPSConnection(host, port, timeout=5, context=context)
    return http.client.HTTPConnection(host, port, timeout=5)


def _exchange(server, body, token=None, headers=None, method="POST", context=None):
    """``(status, headers, raw body)`` of one request."""
    connection = _connection(server, context)
    sent = {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})}
    if token is not None:
        sent["Authorization"] = f"Bearer {token}"
    payload = None if body is None else json.dumps(body)
    connection.request(method, DEFAULT_PATH, body=payload, headers=sent)
    response = connection.getresponse()
    raw = response.read().decode("utf-8")
    connection.close()
    return response.status, dict(response.getheaders()), raw


def _events(raw):
    return [json.loads(chunk[len("data: "):]) for chunk in raw.split("\n\n")
            if chunk.startswith("data: ")]


def _request(method, params=None, msg_id=1):
    return {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}


def _call(name):
    return _request("tools/call", {"name": name, "arguments": {}})


def _audit(server):
    return [json.loads(line) for line in
            server.audit_path.read_text(encoding="utf-8").splitlines()]


# --- a POST answered as an SSE stream ---------------------------------------

def _sse(server, body, token):
    status, headers, raw = _exchange(server, body, token, {"Accept": _SSE})
    return status, headers, _events(raw)


def test_sse_post_needs_a_users_token(serve):
    server = serve(auth_token="shared-secret")
    for token in (None, "shared-secret", "wrong"):
        status, headers, raw = _exchange(server, _request("tools/list"), token, {"Accept": _SSE})
        assert status == 401 and "text/event-stream" not in headers.get("Content-Type", "")
        assert "WWW-Authenticate" in headers and "tools" not in raw


@pytest.mark.parametrize("role", Role.all())
def test_sse_post_lists_and_runs_only_what_the_role_grants(serve, users, role):
    server = serve()
    token = users.tokens[role]
    status, headers, events = _sse(server, _request("tools/list"), token)
    assert status == 200 and "text/event-stream" in headers["Content-Type"]
    assert [tool["name"] for tool in events[-1]["result"]["tools"]] == _VISIBLE[role]
    for name in _ALL:
        _status, _headers, events = _sse(server, _call(name), token)
        assert ("result" in events[-1]) is (name in _VISIBLE[role]), (role, name)
    assert server.calls == [(name, f"{role}-user") for name in _VISIBLE[role]]


def test_sse_post_refusal_names_the_capability_and_is_audited(serve, users):
    server = serve()
    _status, _headers, events = _sse(server, _call("poke"), users.tokens[Role.VIEWER])
    assert events[-1]["error"]["code"] == -32003
    assert events[-1]["error"]["data"] == {"required_capability": Capability.DRIVE_INPUT}
    _sse(server, _call("poke"), users.tokens[Role.OPERATOR])
    refused, ran = _audit(server)
    assert (refused["user_id"], refused["status"]) == ("viewer-user", "denied")
    assert (ran["user_id"], ran["role"], ran["status"]) == ("operator-user", "operator", "ok")


def test_sse_post_refuses_a_privileged_command_inside_the_arguments(serve, users):
    server = serve()
    body = _request("tools/call", {"name": "poke", "arguments": {
        "actions": [["AC_sign_action_file", {"path": "x"}]]}})
    _status, _headers, events = _sse(server, body, users.tokens[Role.OPERATOR])
    assert events[-1]["error"]["data"] == {"required_capability": Capability.SIGN_ACTIONS}
    assert server.calls == []


# --- the session's standing GET stream --------------------------------------

def _initialize(server, token):
    status, headers, raw = _exchange(server, _request("initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "t", "version": "1"}}), token)
    assert status == 200, raw
    return headers["Mcp-Session-Id"]


def test_session_requests_are_authorised_one_by_one(serve, users):
    """A session carries neither a role nor access: each request is its caller's own.

    The operator used to be served inside the admin's session (and refused
    only for the tool's capability); the session id is no longer honoured for
    anyone but the user who created it.
    """
    server = serve()
    session = {"Mcp-Session-Id": _initialize(server, users.tokens[Role.ADMIN])}
    _status, _headers, raw = _exchange(server, _call("ac_load_plugins"),
                                       users.tokens[Role.ADMIN], session)
    assert "result" in json.loads(raw)
    assert _exchange(server, _call("ac_load_plugins"),
                     users.tokens[Role.OPERATOR], session)[0] == 403
    own = {"Mcp-Session-Id": _initialize(server, users.tokens[Role.OPERATOR])}
    status, _headers, raw = _exchange(server, _call("ac_load_plugins"),
                                      users.tokens[Role.OPERATOR], own)
    assert status == 200 and json.loads(raw)["error"]["code"] == -32003
    assert _exchange(server, _call("peek"), None, session)[0] == 401
    assert server.calls == [("ac_load_plugins", "admin-user")]


def test_the_get_stream_and_delete_need_a_users_token(serve, users):
    server = serve(auth_token="shared-secret")
    session = {"Mcp-Session-Id": _initialize(server, users.tokens[Role.VIEWER])}
    stream = {**session, "Accept": "text/event-stream"}
    for token in (None, "shared-secret"):
        assert _exchange(server, None, token, stream, method="GET")[0] == 401
        assert _exchange(server, None, token, session, method="DELETE")[0] == 401
    connection = _connection(server)
    connection.request("GET", DEFAULT_PATH, headers={
        **stream, "Authorization": f"Bearer {users.tokens[Role.VIEWER]}"})
    response = connection.getresponse()
    assert response.status == 200
    assert "text/event-stream" in response.getheader("Content-Type")
    response.close()
    connection.close()
    assert _exchange(server, None, users.tokens[Role.VIEWER], session, method="DELETE")[0] == 200


# --- the stateless revision -------------------------------------------------

def _stateless_headers(method, name=None):
    headers = {"MCP-Protocol-Version": STATELESS_PROTOCOL_VERSION, "Mcp-Method": method}
    if name is not None:
        headers["Mcp-Name"] = name
    return headers


def _stateless(method, params=None, msg_id=1):
    meta = {"io.modelcontextprotocol/protocolVersion": STATELESS_PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientInfo": {"name": "t", "version": "1"},
            "io.modelcontextprotocol/clientCapabilities": {}}
    return {"jsonrpc": "2.0", "id": msg_id, "method": method,
            "params": {**(params or {}), "_meta": meta}}


def test_stateless_requests_need_a_users_token(serve):
    server = serve(auth_token="shared-secret")
    for token in (None, "shared-secret"):
        status, _headers, raw = _exchange(server, _stateless("tools/list"), token,
                                          _stateless_headers("tools/list"))
        assert status == 401 and "tools" not in raw


@pytest.mark.parametrize("role", Role.all())
def test_stateless_lists_and_runs_only_what_the_role_grants(serve, users, role):
    server = serve()
    token = users.tokens[role]
    status, headers, raw = _exchange(server, _stateless("tools/list"), token,
                                     _stateless_headers("tools/list"))
    assert status == 200 and "Mcp-Session-Id" not in headers
    assert [tool["name"] for tool in json.loads(raw)["result"]["tools"]] == _VISIBLE[role]
    for name in ("peek", "ac_load_plugins"):
        body = _stateless("tools/call", {"name": name, "arguments": {}})
        _status, _headers, raw = _exchange(server, body, token,
                                           _stateless_headers("tools/call", name))
        reply = json.loads(raw)
        if name in _VISIBLE[role]:
            assert reply["result"]["isError"] is False
        else:
            assert reply["error"]["code"] == -32003
    expected = [name for name in ("peek", "ac_load_plugins") if name in _VISIBLE[role]]
    assert server.calls == [(name, f"{role}-user") for name in expected]


def test_stateless_sse_reply_is_authorised_too(serve, users):
    server = serve()
    body = _stateless("tools/call", {"name": "peek", "arguments": {}})
    headers = {**_stateless_headers("tools/call", "peek"), "Accept": _SSE}
    status, _headers, raw = _exchange(server, body, users.tokens[Role.VIEWER], headers)
    assert status == 200 and _events(raw)[-1]["result"]["isError"] is False
    assert _exchange(server, body, "wrong", headers)[0] == 401
    assert server.calls == [("peek", "viewer-user")]


# --- subscriptions/listen ---------------------------------------------------

def _open_listen(server, token, context=None):
    connection = _connection(server, context)
    body = json.dumps(_stateless("subscriptions/listen",
                                 {"notifications": {"toolsListChanged": True}}, msg_id=11))
    headers = {"Content-Type": "application/json", "Accept": _SSE,
               **_stateless_headers("subscriptions/listen")}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    connection.request("POST", DEFAULT_PATH, body=body, headers=headers)
    return connection, connection.getresponse()


def _next_event(response):
    while True:
        line = response.fp.readline()
        if not line:
            return None
        if line.startswith(b"data: "):
            return json.loads(line[len(b"data: "):])


def test_listen_is_refused_without_a_users_token_and_opens_no_stream(serve):
    server = serve(auth_token="shared-secret")
    for token in (None, "shared-secret"):
        connection, response = _open_listen(server, token)
        assert response.status == 401
        assert "text/event-stream" not in (response.getheader("Content-Type") or "")
        response.read()
        connection.close()
    assert not server.mcp._listeners  # noqa: SLF001  # reason: the registry is the observable


def test_a_viewer_may_listen_and_gets_only_the_change_signal(serve, users):
    server = serve()
    connection, response = _open_listen(server, users.tokens[Role.VIEWER])
    try:
        assert response.status == 200
        assert _next_event(response)["params"]["notifications"] == {"toolsListChanged": True}
        server.mcp.register_tool(MCPTool(
            name="ac_egress_reset", description="d", handler=lambda: None,
            annotations=DESTRUCTIVE, input_schema=schema({})))
        changed = _next_event(response)
        assert changed["method"] == "notifications/tools/list_changed"
        assert "ac_egress_reset" not in json.dumps(changed), "a signal, not the tool list"
    finally:
        response.close()
        connection.close()
    # What the signal leads to is still filtered by the viewer's role.
    _status, _headers, raw = _exchange(server, _stateless("tools/list"),
                                       users.tokens[Role.VIEWER],
                                       _stateless_headers("tools/list"))
    assert [tool["name"] for tool in json.loads(raw)["result"]["tools"]] == ["peek"]


# --- TLS --------------------------------------------------------------------

@pytest.fixture()
def tls(tmp_path):
    """``(server context, client context)`` for a throwaway loopback certificate."""
    x509 = pytest.importorskip("cryptography.x509", exc_type=ImportError)
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "mcp-rbac-test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName(
            [x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]), critical=False)
        .sign(private_key=key, algorithm=hashes.SHA256()))
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.minimum_version = ssl.TLSVersion.TLSv1_2
    server_context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.minimum_version = ssl.TLSVersion.TLSv1_2
    client_context.load_verify_locations(cafile=str(cert_path))
    return server_context, client_context


def test_rbac_over_tls_json_and_sse(serve, users, tls):
    server_context, client_context = tls
    server = serve(ssl_context=server_context, auth_token="shared-secret")
    for token in (None, "shared-secret"):
        assert _exchange(server, _request("tools/list"), token,
                         context=client_context)[0] == 401
    for role in Role.all():
        _status, _headers, raw = _exchange(server, _request("tools/list"),
                                           users.tokens[role], context=client_context)
        assert [tool["name"] for tool in json.loads(raw)["result"]["tools"]] == _VISIBLE[role]
    status, _headers, raw = _exchange(server, _call("poke"), users.tokens[Role.VIEWER],
                                      {"Accept": _SSE}, context=client_context)
    assert status == 200 and _events(raw)[-1]["error"]["code"] == -32003
    _status, _headers, raw = _exchange(server, _call("poke"), users.tokens[Role.OPERATOR],
                                       {"Accept": _SSE}, context=client_context)
    assert "result" in _events(raw)[-1]
    assert server.calls == [("poke", "operator-user")]


def test_rbac_over_tls_stateless_and_listen(serve, users, tls):
    server_context, client_context = tls
    server = serve(ssl_context=server_context)
    body = _stateless("tools/call", {"name": "ac_load_plugins", "arguments": {}})
    headers = _stateless_headers("tools/call", "ac_load_plugins")
    _status, _headers, raw = _exchange(server, body, users.tokens[Role.OPERATOR], headers,
                                       context=client_context)
    assert json.loads(raw)["error"]["data"] == {"required_capability": Capability.MANAGE_HOSTS}
    _status, _headers, raw = _exchange(server, body, users.tokens[Role.ADMIN], headers,
                                       context=client_context)
    assert json.loads(raw)["result"]["isError"] is False
    connection, response = _open_listen(server, None, context=client_context)
    assert response.status == 401
    connection.close()
    connection, response = _open_listen(server, users.tokens[Role.VIEWER],
                                        context=client_context)
    assert response.status == 200
    assert _next_event(response)["method"] == "notifications/subscriptions/acknowledged"
    response.close()
    connection.close()


def test_a_plain_client_cannot_reach_a_tls_rbac_server(serve, users, tls):
    server = serve(ssl_context=tls[0])
    host, port = server.address
    request = urllib.request.Request(
        f"http://{host}:{port}{DEFAULT_PATH}",  # NOSONAR the point: plaintext is refused
        data=json.dumps(_request("tools/list")).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {users.tokens[Role.ADMIN]}"})
    with pytest.raises((urllib.error.URLError, ConnectionError, http.client.HTTPException,
                        TimeoutError)):
        urllib.request.urlopen(request, timeout=3)  # nosec B310  # reason: loopback test server
