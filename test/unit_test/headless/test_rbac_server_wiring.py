"""RBAC wired into the REST API, the MCP HTTP transport and the executor.

Opt-in: a server with no user store keeps its single shared token. With a
store, a token is one user's, each route / tool / privileged command needs a
capability of that user's role, and the audit entries name the user.

Nothing here touches the real mouse, keyboard or screen: REST handlers that
would are replaced by recorders, and the MCP tools are local fakes.
"""
import json
import urllib.error
import urllib.request

import time

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
from je_auto_control.utils.mcp_server.prompts import StaticPromptProvider
from je_auto_control.utils.mcp_server.resources import ChainProvider
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, build_default_tool_registry
from je_auto_control.utils.mcp_server.tools._base import DESTRUCTIVE, READ_ONLY, schema
from je_auto_control.utils.rbac import (
    USERS_ENV, AuthorizationContext, AuthorizationError, Capability, Role,
    UserStore, authorization_scope, authorize_command, capability_for_route,
    capability_for_tool, current_authorization, denied_command_in,
)
from je_auto_control.utils.rbac.policy import (
    COMMAND_CAPABILITIES, REST_ROUTE_CAPABILITIES, TOOL_CAPABILITIES,
)
from je_auto_control.utils.rest_api import rest_server
from je_auto_control.utils.rest_api.rest_auth import RestAuthGate
from je_auto_control.utils.rest_api.rest_server import RestApiServer

_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS out of scope
_SIGN = "AC_sign_action_file"


@pytest.fixture(autouse=True)
def _no_ambient_rbac(monkeypatch):
    """The developer's own environment must not switch RBAC on for these tests."""
    monkeypatch.delenv(USERS_ENV, raising=False)
    monkeypatch.delenv("JE_AUTOCONTROL_MCP_TOKEN", raising=False)


@pytest.fixture
def users(tmp_path):
    """A store with one user per role; ``tokens`` maps the role to its token."""
    store = UserStore(tmp_path / "users.json")
    store.tokens = {
        role: store.add_user(user_id=f"{role}-user", display_name=role, role=role)
        for role in Role.all()
    }
    return store


class _FakeAudit:
    """Stands in for the tamper-evident audit log; keeps what it was given."""

    def __init__(self):
        self.rows = []

    def log(self, event_type, **fields):
        self.rows.append({"event_type": event_type, **fields})

    def query(self, **_kwargs):
        return list(self.rows)


@pytest.fixture
def rest(monkeypatch):
    """Start REST servers on ephemeral ports; ``/execute`` only records its body."""
    executed = []

    def fake_execute(ctx):
        executed.append(ctx.body)
        return 200, {"result": "ran"}

    monkeypatch.setitem(rest_server._POST_ROUTES, "/execute", fake_execute)
    started = []

    def start(**kwargs):
        server = RestApiServer(host="127.0.0.1", port=0, enable_audit=False, **kwargs)
        server._audit_log = _FakeAudit()
        server.start()
        server.executed = executed
        started.append(server)
        return server

    yield start
    for server in started:
        server.stop(timeout=1.0)


def _call(server, method, path, token=None, body=None):
    """``(status, decoded JSON)`` of one request; an error status is returned, not raised."""
    host, port = server.address
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{_SCHEME}://{host}:{port}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310  # reason: loopback test server
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


# --- REST ---------------------------------------------------------------

def test_unconfigured_rbac_keeps_shared_token(rest):
    server = rest(token="shared-secret")
    assert server.user_store is None
    assert _call(server, "GET", "/commands", "shared-secret")[0] == 200
    status, _body = _call(server, "POST", "/execute", "shared-secret", {"actions": [[_SIGN]]})
    assert status == 200, "the shared token is not restricted by any role"
    assert _call(server, "GET", "/commands", "wrong")[0] == 401
    assert "user=" not in server._audit_log.rows[0]["detail"]
    assert "viewer_id" not in server._audit_log.rows[0]


def test_viewer_cannot_execute(rest, users):
    server = rest(user_store=users)
    viewer = users.tokens[Role.VIEWER]
    assert _call(server, "GET", "/commands", viewer)[0] == 200
    status, body = _call(server, "POST", "/execute", viewer,
                         {"actions": [["AC_slugify", {"text": "x"}]]})
    assert status == 403
    assert body == {"error": "forbidden", "role": Role.VIEWER,
                    "required_capability": Capability.DRIVE_INPUT}
    assert server.executed == []


def test_operator_executes_but_cannot_sign(rest, users, tmp_path):
    server = rest(user_store=users)
    operator = users.tokens[Role.OPERATOR]
    target = tmp_path / "actions.json"
    target.write_text("[]", encoding="utf-8")
    assert _call(server, "POST", "/execute", operator,
                 {"actions": [["AC_slugify", {"text": "x"}]]})[0] == 200
    assert len(server.executed) == 1
    nested = {"actions": [["AC_loop", {"times": 1, "body": [[_SIGN, {"path": str(target)}]]}]]}
    status, body = _call(server, "POST", "/execute", operator, nested)
    assert status == 403
    assert body["required_capability"] == Capability.SIGN_ACTIONS
    assert body["command"] == _SIGN
    assert len(server.executed) == 1, "the refused list must not reach the handler"


def test_admin_may_sign_and_shared_token_is_refused_under_rbac(rest, users):
    server = rest(user_store=users, token="shared-secret")
    admin = users.tokens[Role.ADMIN]
    assert _call(server, "POST", "/execute", admin, {"actions": [[_SIGN]]})[0] == 200
    assert _call(server, "GET", "/commands", "shared-secret")[0] == 401
    assert _call(server, "GET", "/commands")[0] == 401


@pytest.mark.parametrize("role,path,expected", [
    (Role.VIEWER, "/audit/list", 403),
    (Role.OPERATOR, "/audit/list", 403),
    (Role.OPERATOR, "/metrics", 200),
    (Role.ADMIN, "/metrics", 200),
])
def test_get_routes_follow_the_role(rest, users, role, path, expected):
    server = rest(user_store=users)
    assert _call_status(server, path, users.tokens[role]) == expected


def _call_status(server, path, token):
    host, port = server.address
    request = urllib.request.Request(
        f"{_SCHEME}://{host}:{port}{path}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310  # reason: loopback test server
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_operator_cannot_sign_through_an_action_file(users, tmp_path):
    """The file's content is never seen by the server: the executor refuses it."""
    target = tmp_path / "payload.json"
    target.write_text("[]", encoding="utf-8")
    script = tmp_path / "script.json"
    script.write_text(json.dumps(
        [["AC_parallel", {"branches": [[[_SIGN, {"path": str(target), "key": "k"}]]]}],
         [_SIGN, {"path": str(target), "key": "k"}]]), encoding="utf-8")
    operator = AuthorizationContext("operator-user", Role.OPERATOR)
    with authorization_scope(operator):
        executor.execute_files([str(script)])
    assert not (tmp_path / "payload.json.sig").exists()
    with authorization_scope(AuthorizationContext("admin-user", Role.ADMIN)):
        executor.execute_files([str(script)])
    assert (tmp_path / "payload.json.sig").exists()


def test_executor_check_is_typed_and_silent_outside_a_scope():
    authorize_command(_SIGN)  # no scope: the library used directly is unrestricted
    assert current_authorization() is None
    with authorization_scope(AuthorizationContext("op", Role.OPERATOR)):
        authorize_command("AC_click_mouse")
        with pytest.raises(AuthorizationError) as raised:
            authorize_command(_SIGN)
        assert raised.value.capability == Capability.SIGN_ACTIONS
        assert isinstance(raised.value, (AutoControlException, PermissionError))
        with authorization_scope(None):
            authorize_command(_SIGN)
    assert current_authorization() is None


def test_rest_audit_rows_name_the_user(rest, users):
    server = rest(user_store=users)
    _call(server, "GET", "/commands", users.tokens[Role.OPERATOR])
    _call(server, "POST", "/execute", users.tokens[Role.VIEWER], {"actions": []})
    # The row is written after the response is sent, so the client can be
    # back here before the second one exists.
    deadline = time.monotonic() + 5.0
    while len(server._audit_log.rows) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    allowed, refused = server._audit_log.rows
    assert allowed["viewer_id"] == "operator-user"
    assert "user=operator-user role=operator" in allowed["detail"]
    assert refused["viewer_id"] == "viewer-user"
    assert "forbidden:drive_input" in refused["detail"]


def test_user_changes_apply_without_a_restart(rest, users):
    server = rest(user_store=users)
    viewer = users.tokens[Role.VIEWER]
    assert _call(server, "GET", "/commands", viewer)[0] == 200
    # Another process manages the users: a second store on the same file.
    manager = UserStore(users.path)
    manager.set_role("viewer-user", Role.OPERATOR)
    assert _call(server, "POST", "/execute", viewer, {"actions": []})[0] == 200
    manager.remove_user("viewer-user")
    assert _call(server, "GET", "/commands", viewer)[0] == 401


def test_broken_or_empty_store_admits_nobody(rest, tmp_path):
    path = tmp_path / "users.json"
    path.write_text("{not json", encoding="utf-8")
    server = rest(user_store=UserStore(path), token="shared-secret")
    assert _call(server, "GET", "/commands", "shared-secret")[0] == 401


def test_environment_variable_switches_rbac_on(monkeypatch, users):
    assert RestApiServer(enable_audit=False).user_store is None
    assert HttpMCPServer(mcp=_mcp([]))._users is None
    monkeypatch.setenv(USERS_ENV, str(users.path))
    assert RestApiServer(enable_audit=False).user_store.path == users.path.resolve()
    assert HttpMCPServer(mcp=_mcp([]))._users.path == users.path.resolve()


def test_gate_check_keeps_its_string_verdicts(users):
    gate = RestAuthGate("shared", user_store=users)
    header = f"Bearer {users.tokens[Role.VIEWER]}"
    assert gate.rbac_enabled
    assert gate.check(client_ip="1.1.1.1", header_value=header) == "ok"
    assert gate.check(client_ip="1.1.1.1", header_value="Bearer shared") == "unauthorized"
    result = gate.authenticate(client_ip="1.1.1.1", header_value=header)
    assert result.context == AuthorizationContext("viewer-user", Role.VIEWER)
    legacy = RestAuthGate("shared").authenticate(client_ip="1.1.1.1", header_value="Bearer shared")
    assert (legacy.verdict, legacy.context) == ("ok", None)


# --- the policy tables --------------------------------------------------

def test_every_rest_route_has_a_decided_capability():
    routes = {("GET", path) for path in rest_server._GET_ROUTES}
    routes |= {("POST", path) for path in rest_server._POST_ROUTES}
    routes.add(("GET", "/metrics"))
    routes -= {("GET", path) for path in rest_server._PUBLIC_PATHS}
    assert routes == set(REST_ROUTE_CAPABILITIES)
    assert capability_for_route("POST", "/not/listed") == Capability.MANAGE_HOSTS


def test_policy_tables_name_things_that_exist():
    assert set(COMMAND_CAPABILITIES) <= executor.known_commands()
    assert set(TOOL_CAPABILITIES) <= {tool.name for tool in build_default_tool_registry()}
    known = set(Capability.all())
    assert set(COMMAND_CAPABILITIES.values()) | set(TOOL_CAPABILITIES.values()) <= known
    assert set(REST_ROUTE_CAPABILITIES.values()) <= known


def test_only_admin_holds_the_signing_capability():
    assert capability_for_tool("anything", read_only=True) == Capability.READ_SCREEN
    assert capability_for_tool("anything", read_only=False) == Capability.DRIVE_INPUT
    holders = [role for role in Role.all()
               if AuthorizationContext("u", role).allows(Capability.SIGN_ACTIONS)]
    assert holders == [Role.ADMIN]


def test_denied_command_is_found_wherever_a_list_nests():
    operator = AuthorizationContext("op", Role.OPERATOR)
    assert denied_command_in({"actions": [["AC_click_mouse"]]}, operator) is None
    deep = {"spec": {"steps": [{"then": [["AC_try", {"body": [[_SIGN, {}]]}]]}]}}
    assert denied_command_in(deep, operator) == (_SIGN, Capability.SIGN_ACTIONS)
    assert denied_command_in(deep, AuthorizationContext("root", Role.ADMIN)) is None


# --- MCP ----------------------------------------------------------------

def _mcp(tools, audit_path=None):
    return MCPServer(tools=tools, resource_provider=ChainProvider([]),
                     prompt_provider=StaticPromptProvider([]),
                     audit_logger=AuditLogger(path=audit_path))


@pytest.fixture
def mcp_http(tmp_path):
    """Start MCP HTTP servers over three fake tools; ``calls`` records invocations."""
    calls = []

    def tool(name, annotations):
        def handler(**arguments):
            calls.append((name, arguments))
            return {"ran": name}
        return MCPTool(name=name, description=name, annotations=annotations, handler=handler,
                       input_schema=schema({"actions": {"type": "array"}}))

    tools = [tool("peek", READ_ONLY), tool("poke", DESTRUCTIVE),
             tool("ac_load_plugins", DESTRUCTIVE)]
    audit_path = tmp_path / "mcp_audit.jsonl"
    started = []

    def start(**kwargs):
        server = HttpMCPServer(mcp=_mcp(tools, str(audit_path)), host="127.0.0.1", port=0,
                               **kwargs)
        server.start()
        server.calls = calls
        server.audit_path = audit_path
        started.append(server)
        return server

    yield start
    for server in started:
        server.stop(timeout=1.0)


def _rpc(server, method, params=None, token=None):
    return _call(server, "POST", DEFAULT_PATH, token,
                 {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def _tool_names(server, token):
    _status, body = _rpc(server, "tools/list", token=token)
    return [tool["name"] for tool in body["result"]["tools"]]


def _audit_entries(server):
    return [json.loads(line) for line in
            server.audit_path.read_text(encoding="utf-8").splitlines()]


def test_mcp_tool_list_matches_what_each_role_may_call(mcp_http, users):
    server = mcp_http(user_store=users)
    expected = {Role.VIEWER: ["peek"], Role.OPERATOR: ["peek", "poke"],
                Role.ADMIN: ["peek", "poke", "ac_load_plugins"]}
    for role, names in expected.items():
        token = users.tokens[role]
        assert _tool_names(server, token) == names
        for name in ("peek", "poke", "ac_load_plugins"):
            _status, body = _rpc(server, "tools/call", {"name": name, "arguments": {}}, token)
            assert ("result" in body) is (name in names), (role, name, body)


def test_mcp_viewer_cannot_execute(mcp_http, users):
    server = mcp_http(user_store=users)
    status, body = _rpc(server, "tools/call", {"name": "poke", "arguments": {}},
                        users.tokens[Role.VIEWER])
    assert status == 200
    assert body["error"]["code"] == -32003
    assert body["error"]["data"] == {"required_capability": Capability.DRIVE_INPUT}
    assert server.calls == []


def test_mcp_operator_cannot_sign_through_an_action_list(mcp_http, users):
    server = mcp_http(user_store=users)
    arguments = {"actions": [["AC_if_var", {"then": [[_SIGN, {"path": "x"}]]}]]}
    _status, body = _rpc(server, "tools/call", {"name": "poke", "arguments": arguments},
                         users.tokens[Role.OPERATOR])
    assert body["error"]["data"] == {"required_capability": Capability.SIGN_ACTIONS}
    assert server.calls == []
    _status, body = _rpc(server, "tools/call", {"name": "poke", "arguments": arguments},
                         users.tokens[Role.ADMIN])
    assert "result" in body
    assert len(server.calls) == 1


def test_user_id_in_audit(mcp_http, users):
    server = mcp_http(user_store=users)
    _rpc(server, "tools/call", {"name": "poke", "arguments": {}}, users.tokens[Role.OPERATOR])
    _rpc(server, "tools/call", {"name": "poke", "arguments": {}}, users.tokens[Role.VIEWER])
    ran, refused = _audit_entries(server)
    assert (ran["user_id"], ran["role"], ran["status"]) == ("operator-user", "operator", "ok")
    assert (refused["user_id"], refused["status"]) == ("viewer-user", "denied")
    assert "drive_input" in refused["error"]


def test_mcp_rbac_refuses_the_shared_token_and_unknown_roles(mcp_http, users):
    users.add_user(user_id="odd", display_name="odd", role=Role.VIEWER, token="odd-token")
    stored = json.loads(users.path.read_text(encoding="utf-8"))
    stored["users"][-1]["role"] = "superuser"
    users.path.write_text(json.dumps(stored), encoding="utf-8")
    server = mcp_http(user_store=users, auth_token="shared-secret")
    assert _rpc(server, "tools/list", token="shared-secret")[0] == 401
    assert _rpc(server, "tools/list")[0] == 401
    assert _rpc(server, "tools/list", token="odd-token")[0] == 403


def test_mcp_unconfigured_rbac_keeps_shared_token(mcp_http):
    server = mcp_http(auth_token="shared-secret")
    assert _rpc(server, "tools/list")[0] == 401
    assert _tool_names(server, "shared-secret") == ["peek", "poke", "ac_load_plugins"]
    _status, body = _rpc(server, "tools/call", {"name": "ac_load_plugins", "arguments": {}},
                         "shared-secret")
    assert "result" in body
    assert "user_id" not in _audit_entries(server)[0]
    assert _tool_names(mcp_http(), None) == ["peek", "poke", "ac_load_plugins"]


def test_default_registry_offers_a_viewer_only_read_only_tools(users):
    """Read-only, and not one of those listed as needing more than ``read_screen``."""
    registry = build_default_tool_registry(read_only=False)
    with authorization_scope(AuthorizationContext("viewer-user", Role.VIEWER)):
        listed = MCPServer(tools=registry).handle_line(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    names = {tool["name"] for tool in json.loads(listed)["result"]["tools"]}
    read_only = {tool.name for tool in registry if tool.annotations.read_only}
    assert names == read_only - set(TOOL_CAPABILITIES)
    assert names < read_only, "data tools and user listing are held back"
    assert "ac_execute_actions" not in names
    assert "ac_click_mouse" not in names
