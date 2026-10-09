"""Managing RBAC users through AC_*, MCP, REST and the CLI; the viewer's tool set.

``Capability.MANAGE_USERS`` existed with no route, tool or command behind it:
users could only be managed from Python. Tokens are shown once, when issued,
and reach neither the log nor an audit entry.

Also here: read-only MCP tools that hand back data rather than screen state
need ``read_data``, a REST gate that only implements ``check()`` is accepted
again, and the REST status no longer reports a shared token RBAC refuses.

Nothing here touches the real mouse, keyboard or screen.
"""
import json
import logging
import urllib.error
import urllib.request

import pytest

from je_auto_control import cli
from je_auto_control.utils.executor.action_executor import execute_action, executor
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, build_default_tool_registry
from je_auto_control.utils.rbac import (
    USERS_ENV, AuthorizationContext, AuthorizationError, Capability, IssuedToken,
    Role, UserAuthError, UserStore, admin, authorization_scope, can,
    capability_for_tool, resolve_token,
)
from je_auto_control.utils.rbac import cli as rbac_cli
from je_auto_control.utils.rbac.policy import (
    COMMAND_CAPABILITIES, DATA_TOOLS, TOOL_CAPABILITIES,
)
from je_auto_control.utils.rest_api import rest_server
from je_auto_control.utils.rest_api.rest_auth import AuthResult, authenticate_with
from je_auto_control.utils.rest_api.rest_registry import rest_api_registry
from je_auto_control.utils.rest_api.rest_server import RestApiServer

_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS out of scope
_USER_COMMANDS = ("AC_user_add", "AC_user_remove", "AC_user_set_role",
                  "AC_user_rotate_token", "AC_user_list")
_USER_TOOLS = tuple(name.replace("AC_", "ac_") for name in _USER_COMMANDS)
_REAL_AUDIT = admin._audit  # the autouse fixture below replaces it


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """No ambient RBAC, and no row written to the developer's real audit database."""
    monkeypatch.delenv(USERS_ENV, raising=False)
    monkeypatch.delenv("JE_AUTOCONTROL_MCP_TOKEN", raising=False)
    events = []
    monkeypatch.setattr(admin, "_audit",
                        lambda event, user_id, detail: events.append((event, user_id, detail)))
    return events


@pytest.fixture()
def users(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.tokens = {
        role: store.add_user(user_id=f"{role}-user", display_name=role, role=role)
        for role in Role.all()
    }
    return store


def _as(users, role):
    return authorization_scope(resolve_token(users, users.tokens[role]))


# --- the headless core ------------------------------------------------------

def test_bootstrap_then_manage_without_any_scope(tmp_path, _isolated):
    path = str(tmp_path / "new" / "users.json")
    issued = admin.add_user("alice", role=Role.ADMIN, display_name="Alice",
                            tags=["ops"], users_path=path)
    assert issued["role"] == Role.ADMIN and issued["tags"] == ["ops"]
    assert UserStore(path).authenticate(issued["token"]).user_id == "alice"
    admin.add_user("bob", users_path=path)
    assert admin.set_user_role("bob", Role.OPERATOR, users_path=path) == {
        "user_id": "bob", "role": "operator"}
    rotated = admin.rotate_user_token("bob", users_path=path)
    assert UserStore(path).authenticate(rotated["token"]).role == Role.OPERATOR
    assert admin.list_users(users_path=path) == [
        {"user_id": "alice", "display_name": "Alice", "role": "admin", "tags": ["ops"]},
        {"user_id": "bob", "display_name": "bob", "role": "operator", "tags": []},
    ]
    assert admin.remove_user("bob", users_path=path) == {"user_id": "bob", "removed": True}
    assert admin.remove_user("bob", users_path=path)["removed"] is False
    assert [event for event, _user, _detail in _isolated] == [
        "user_added", "user_added", "user_role_set", "user_token_rotated", "user_removed"]


def test_no_store_named_is_an_error_not_the_default_location():
    with pytest.raises(UserAuthError, match="JE_AUTOCONTROL_RBAC_USERS"):
        admin.list_users()


def test_the_environment_names_the_store(users, monkeypatch):
    monkeypatch.setenv(USERS_ENV, str(users.path))
    assert len(admin.list_users()) == 3


def test_the_last_admin_cannot_be_removed_or_demoted(users):
    path = str(users.path)
    with pytest.raises(UserAuthError, match="only admin"):
        admin.remove_user("admin-user", users_path=path)
    with pytest.raises(UserAuthError, match="only admin"):
        admin.set_user_role("admin-user", Role.OPERATOR, users_path=path)
    admin.set_user_role("admin-user", Role.ADMIN, users_path=path)
    admin.set_user_role("operator-user", Role.ADMIN, users_path=path)
    assert admin.remove_user("admin-user", users_path=path)["removed"] is True


def test_only_an_admin_manages_users_and_only_its_own_store(users, tmp_path):
    for role in (Role.VIEWER, Role.OPERATOR):
        with _as(users, role), pytest.raises(AuthorizationError) as refused:
            admin.list_users()
        assert refused.value.capability == Capability.MANAGE_USERS
    with _as(users, Role.ADMIN):
        assert len(admin.list_users()) == 3
        assert len(admin.list_users(users_path=str(users.path))) == 3
        with pytest.raises(AuthorizationError, match="another file"):
            admin.add_user("x", users_path=str(tmp_path / "elsewhere.json"))
    assert not (tmp_path / "elsewhere.json").exists()


def test_only_admin_holds_manage_users():
    assert [role for role in Role.all() if can(role, Capability.MANAGE_USERS)] == [Role.ADMIN]


# --- a token is shown once and never logged ---------------------------------

def test_an_issued_token_serialises_but_does_not_print(tmp_path):
    issued = admin.add_user("alice", role=Role.ADMIN, users_path=str(tmp_path / "u.json"))
    assert isinstance(issued, IssuedToken)
    token = issued["token"]
    assert json.loads(json.dumps(issued))["token"] == token
    for text in (str(issued), repr(issued), f"{issued}", "%s" % (issued,), str({"r": issued})):
        assert token not in text and "<shown once>" in text


def test_the_executor_returns_the_token_and_logs_none_of_it(tmp_path, caplog):
    path = str(tmp_path / "u.json")
    autocontrol_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
            record = execute_action([
                ["AC_user_add", {"user_id": "alice", "role": "admin", "users_path": path}],
                ["AC_user_rotate_token", {"user_id": "alice", "users_path": path}],
                ["AC_user_list", {"users_path": path}],
            ])
    finally:
        autocontrol_logger.removeHandler(caplog.handler)
    added, rotated, listed = record.values()
    assert listed == [{"user_id": "alice", "display_name": "alice", "role": "admin", "tags": []}]
    assert UserStore(path).authenticate(rotated["token"]).user_id == "alice"
    logged = "\n".join(entry.getMessage() for entry in caplog.records)
    assert "AC_user_add" in logged, "the run was logged"
    assert added["token"] not in logged and rotated["token"] not in logged
    assert added["token"] not in (tmp_path / "u.json").read_text(encoding="utf-8")


def test_the_real_audit_writer_is_given_no_token(tmp_path, monkeypatch):
    rows = []

    class _Audit:
        def log(self, event_type, **fields):
            rows.append((event_type, fields))

    from je_auto_control.utils.remote_desktop import audit_log
    monkeypatch.setattr(audit_log, "default_audit_log", _Audit)
    monkeypatch.setattr(admin, "_audit", _REAL_AUDIT)
    issued = admin.add_user("alice", role=Role.ADMIN, users_path=str(tmp_path / "u.json"))
    rotated = admin.rotate_user_token("alice", users_path=str(tmp_path / "u.json"))
    assert [event for event, _fields in rows] == ["rbac_user_added", "rbac_user_token_rotated"]
    assert rows[0][1] == {"viewer_id": "local", "detail": "user=alice role=admin"}
    assert issued["token"] not in json.dumps(rows) and rotated["token"] not in json.dumps(rows)


# --- AC_* commands ----------------------------------------------------------

def test_the_commands_exist_and_need_manage_users():
    for name in _USER_COMMANDS:
        assert name in executor.known_commands()
        assert COMMAND_CAPABILITIES[name] == Capability.MANAGE_USERS


def test_an_operator_cannot_run_a_user_command_and_an_admin_can(users):
    action = [["AC_user_set_role", {"user_id": "viewer-user", "role": "operator"}]]
    with _as(users, Role.OPERATOR):
        refused = execute_action(action)
    assert "manage_users" in str(list(refused.values())[0])
    assert users.get("viewer-user").role == Role.VIEWER
    with _as(users, Role.ADMIN):
        execute_action(action)
    assert users.get("viewer-user").role == Role.OPERATOR


# --- REST -------------------------------------------------------------------

def _call(server, method, path, token=None, body=None):
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


class _FakeAudit:
    def __init__(self):
        self.rows = []

    def log(self, event_type, **fields):
        self.rows.append({"event_type": event_type, **fields})


@pytest.fixture()
def rest():
    started = []

    def start(**kwargs):
        server = RestApiServer(host="127.0.0.1", port=0, enable_audit=False, **kwargs)
        server._audit_log = _FakeAudit()
        server.start()
        started.append(server)
        return server

    yield start
    for server in started:
        server.stop(timeout=1.0)


def test_users_are_managed_over_rest_by_an_admin_only(rest, users):
    server = rest(user_store=users)
    body = {"actions": [["AC_user_add", {"user_id": "carol", "role": "operator"}]]}
    status, reply = _call(server, "POST", "/execute", users.tokens[Role.OPERATOR], body)
    assert status == 403 and reply["required_capability"] == Capability.MANAGE_USERS
    assert users.get("carol") is None
    status, reply = _call(server, "POST", "/execute", users.tokens[Role.ADMIN], body)
    assert status == 200
    token = list(reply["result"].values())[0]["token"]
    assert _call(server, "GET", "/commands", token)[0] == 200, "the new user signs in"
    assert token not in json.dumps(server._audit_log.rows)
    # Demoted through the same surface, it applies to the very next request.
    demote = {"actions": [["AC_user_set_role", {"user_id": "carol", "role": "viewer"}]]}
    assert _call(server, "POST", "/execute", users.tokens[Role.ADMIN], demote)[0] == 200
    assert _call(server, "POST", "/execute", token, {"actions": [["AC_user_list"]]})[0] == 403


# --- MCP --------------------------------------------------------------------

@pytest.fixture()
def mcp_http(tmp_path):
    registry = [tool for tool in build_default_tool_registry(read_only=False, aliases=False)
                if tool.name in _USER_TOOLS]
    audit_path = tmp_path / "mcp_audit.jsonl"
    started = []

    def start(**kwargs):
        server = HttpMCPServer(
            mcp=MCPServer(tools=registry, audit_logger=AuditLogger(path=str(audit_path))),
            host="127.0.0.1", port=0, **kwargs)
        server.start()
        server.audit_path = audit_path
        started.append(server)
        return server

    yield start
    for server in started:
        server.stop(timeout=1.0)


def _rpc(server, method, params=None, token=None):
    return _call(server, "POST", DEFAULT_PATH, token,
                 {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def _tool_result(body):
    return json.loads(body["result"]["content"][0]["text"])


def test_the_mcp_tools_are_offered_to_an_admin_only(mcp_http, users):
    server = mcp_http(user_store=users)
    for role in (Role.VIEWER, Role.OPERATOR):
        _status, body = _rpc(server, "tools/list", token=users.tokens[role])
        assert body["result"]["tools"] == []
        _status, body = _rpc(server, "tools/call",
                             {"name": "ac_user_list", "arguments": {}}, users.tokens[role])
        assert body["error"]["data"] == {"required_capability": Capability.MANAGE_USERS}
    _status, body = _rpc(server, "tools/list", token=users.tokens[Role.ADMIN])
    assert sorted(tool["name"] for tool in body["result"]["tools"]) == sorted(_USER_TOOLS)


def test_an_admin_manages_users_over_mcp_and_the_audit_holds_no_token(mcp_http, users):
    server = mcp_http(user_store=users)
    admin_token = users.tokens[Role.ADMIN]
    _status, body = _rpc(server, "tools/call", {
        "name": "ac_user_add", "arguments": {"user_id": "dave", "role": "viewer"}}, admin_token)
    added = _tool_result(body)
    assert added["user_id"] == "dave" and users.authenticate(added["token"]).role == Role.VIEWER
    _status, body = _rpc(server, "tools/call", {
        "name": "ac_user_rotate_token", "arguments": {"user_id": "dave"}}, admin_token)
    rotated = _tool_result(body)
    assert rotated["token"] != added["token"]
    assert _rpc(server, "tools/list", token=added["token"])[0] == 401, "the old token is dead"
    _status, body = _rpc(server, "tools/call", {
        "name": "ac_user_set_role", "arguments": {"user_id": "dave", "role": "admin"}},
        admin_token)
    assert _tool_result(body) == {"user_id": "dave", "role": "admin"}
    _status, body = _rpc(server, "tools/call", {"name": "ac_user_list", "arguments": {}},
                         rotated["token"])
    assert "dave" in [user["user_id"] for user in _tool_result(body)["users"]]
    _status, body = _rpc(server, "tools/call", {
        "name": "ac_user_remove", "arguments": {"user_id": "dave"}}, admin_token)
    assert _tool_result(body) == {"user_id": "dave", "removed": True}
    audit = server.audit_path.read_text(encoding="utf-8")
    assert added["token"] not in audit and rotated["token"] not in audit
    assert all(json.loads(line)["user_id"] for line in audit.splitlines())


def test_without_rbac_the_tools_need_a_named_store(mcp_http):
    """No user store on the server: nothing is authorised, and nothing is guessed."""
    server = mcp_http()
    _status, body = _rpc(server, "tools/call", {"name": "ac_user_list", "arguments": {}})
    assert body["result"]["isError"] is True
    assert "JE_AUTOCONTROL_RBAC_USERS" in body["result"]["content"][0]["text"]


# --- the CLI ----------------------------------------------------------------

def test_the_cli_bootstraps_the_first_admin(tmp_path, capsys):
    path = str(tmp_path / "users.json")
    assert cli.main(["users", "--users", path, "add", "alice", "--role", "admin",
                     "--name", "Alice"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("alice: token (shown once")
    assert UserStore(path).authenticate(out[1]).role == Role.ADMIN
    assert cli.main(["users", "--users", path, "--json", "add", "bob"]) == 0
    bob = json.loads(capsys.readouterr().out)
    assert bob["role"] == Role.VIEWER and UserStore(path).authenticate(bob["token"])
    assert cli.main(["users", "--users", path, "set-role", "bob", "operator"]) == 0
    assert cli.main(["users", "--users", path, "rotate-token", "bob"]) == 0
    rotated = capsys.readouterr().out.splitlines()[-1]
    assert UserStore(path).authenticate(rotated).role == Role.OPERATOR
    assert cli.main(["users", "--users", path, "list"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "alice\tadmin\tAlice", "bob\toperator\tbob"]
    assert cli.main(["users", "--users", path, "remove", "bob"]) == 0
    assert cli.main(["users", "--users", path, "remove", "bob"]) == 1


def test_the_cli_reports_errors_without_a_traceback(tmp_path, capsys, monkeypatch):
    path = str(tmp_path / "users.json")
    assert cli.main(["users", "list"]) == 1
    assert "JE_AUTOCONTROL_RBAC_USERS" in capsys.readouterr().err
    cli.main(["users", "--users", path, "add", "alice", "--role", "admin"])
    assert cli.main(["users", "--users", path, "remove", "alice"]) == 1
    assert "only admin" in capsys.readouterr().err
    monkeypatch.setenv(USERS_ENV, path)
    assert rbac_cli.main(["list"]) == 0, "python -m je_auto_control.utils.rbac"
    assert capsys.readouterr().out == "alice\tadmin\talice\n"
    assert rbac_cli.main(["set-role", "nobody", "viewer"]) == 1


# --- the viewer's tool set --------------------------------------------------

def test_data_tools_need_more_than_read_screen(users):
    registry = build_default_tool_registry(read_only=False)
    by_name = {tool.name: tool for tool in registry}
    assert DATA_TOOLS <= set(by_name), sorted(DATA_TOOLS - set(by_name))
    for name in ("ac_sql_query", "ac_load_dotenv", "ac_get_clipboard", "ac_jwt_encode"):
        assert name in DATA_TOOLS
    for name in DATA_TOOLS:
        assert by_name[name].annotations.read_only, f"{name} is covered by drive_input already"
        assert capability_for_tool(name, True) == Capability.READ_DATA
    assert can(Role.VIEWER, Capability.READ_DATA) is False
    assert can(Role.OPERATOR, Capability.READ_DATA) and can(Role.ADMIN, Capability.READ_DATA)
    with authorization_scope(AuthorizationContext("viewer-user", Role.VIEWER)):
        listed = MCPServer(tools=registry).handle_line(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    names = {tool["name"] for tool in json.loads(listed)["result"]["tools"]}
    assert not names & DATA_TOOLS
    assert {"ac_screen_size", "ac_list_windows", "ac_get_pixel", "screenshot"} - names == {
        "screenshot"}, "screen-state tools stay; the screenshot tool is not read-only"


_STORED_RECORD_TOOLS = (
    # the ones the maintainer named
    "ac_list_run_history", "ac_costs_list", "ac_costs_summary", "ac_trace_export",
    "ac_self_heal_log_list", "ac_usb_acl_list",
    # the rest of the registry that meets the same rule
    "ac_trace_summary", "ac_heal_stats", "ac_self_heal_revision_list",
    "ac_self_heal_evaluate", "ac_flaky_report", "ac_rank_tests", "ac_select_tests",
    "ac_shard_suite", "ac_ab_report", "ac_ab_best_strategy", "ac_journal_read",
    "ac_journal_runs", "ac_lease_active", "ac_element_list", "ac_skill_list",
    "ac_skill_search", "ac_repair_pending", "ac_repair_resolved", "ac_quarantine_list",
    "ac_pending_artifacts", "ac_config_sync_status",
    "ac_android_get_clipboard", "ac_ios_get_clipboard",
)
_LIVE_SCREEN_TOOLS = (
    "ac_vlm_locate", "ac_self_heal_locate",  # they read the screen; cost is not a capability
    "ac_locate_text", "ac_locate_image_center", "ac_a11y_list", "ac_element_find",
    "ac_list_executions", "ac_scheduler_list_jobs", "ac_journal_status",
)


def test_stored_records_need_read_data_and_the_live_screen_only_read_screen():
    registry = {tool.name: tool for tool in build_default_tool_registry(read_only=False)}
    for name in _STORED_RECORD_TOOLS:
        assert registry[name].annotations.read_only, name
        assert capability_for_tool(name, True) == Capability.READ_DATA, name
    for name in _LIVE_SCREEN_TOOLS:
        assert registry[name].annotations.read_only, name
        assert capability_for_tool(name, True) == Capability.READ_SCREEN, name
    assert len(DATA_TOOLS) == 71


def test_a_viewer_is_refused_a_stored_record_tool_and_an_operator_is_not():
    ran = []

    def handler():
        ran.append("history")
        return []

    registry = [tool for tool in build_default_tool_registry(read_only=False)
                if tool.name == "ac_list_run_history"]
    server = MCPServer(tools=[MCPTool(
        name=registry[0].name, description="history", input_schema={"type": "object"},
        handler=handler, annotations=registry[0].annotations)])
    call = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "ac_list_run_history", "arguments": {}}})
    with authorization_scope(AuthorizationContext("viewer-user", Role.VIEWER)):
        refused = json.loads(server.handle_line(call))
    assert refused["error"]["code"] == -32003
    assert refused["error"]["data"]["required_capability"] == Capability.READ_DATA
    assert ran == []
    with authorization_scope(AuthorizationContext("op", Role.OPERATOR)):
        allowed = json.loads(server.handle_line(call))
    assert allowed["result"]["isError"] is False and ran == ["history"]


def test_an_alias_needs_what_its_tool_needs():
    from je_auto_control.utils.mcp_server.tools import _DEFAULT_ALIASES
    registry = {tool.name: tool for tool in build_default_tool_registry(read_only=False)}
    for alias, canonical in _DEFAULT_ALIASES.items():
        read_only = registry[canonical].annotations.read_only
        assert capability_for_tool(alias, read_only) == capability_for_tool(
            canonical, read_only), alias
    assert set(TOOL_CAPABILITIES) <= set(registry), "every listed tool exists"


# --- a gate that only implements check() ------------------------------------

class _CheckOnlyGate:
    """A gate written before ``authenticate`` existed."""

    def check(self, *, client_ip, header_value):
        return "ok" if header_value == "Bearer legacy" else "unauthorized"


def test_authenticate_with_falls_back_to_check():
    gate = _CheckOnlyGate()
    assert authenticate_with(gate, client_ip="1", header_value="Bearer legacy") == AuthResult("ok")
    assert authenticate_with(gate, client_ip="1", header_value=None).verdict == "unauthorized"


def test_a_check_only_gate_serves_requests(rest, monkeypatch):
    monkeypatch.setitem(rest_server._POST_ROUTES, "/execute",
                        lambda ctx: (200, {"result": "ran"}))
    server = rest(token="unused")
    server._server.auth_gate = _CheckOnlyGate()
    assert _call(server, "POST", "/execute", "legacy", {"actions": []}) == (
        200, {"result": "ran"})
    assert _call(server, "POST", "/execute", "wrong", {"actions": []})[0] == 401


# --- the REST status says how to authenticate -------------------------------

def test_status_reports_rbac_instead_of_a_token_that_is_refused(users):
    try:
        shared = rest_api_registry.start(port=0, token="shared", enable_audit=False)
        assert (shared["token"], shared["rbac"], shared["users_path"]) == ("shared", False, None)
        status = rest_api_registry.start(port=0, token="shared", enable_audit=False,
                                         user_store=users)
        assert status["running"] is True and status["rbac"] is True
        assert status["token"] is None and status["users_path"] == str(users.path)
    finally:
        stopped = rest_api_registry.stop()
    assert stopped["rbac"] is False and stopped["token"] is None
