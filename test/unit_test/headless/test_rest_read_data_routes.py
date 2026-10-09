"""REST routes that return stored records need ``read_data``, as the MCP tools do.

A viewer token could read the run history and the USB ACL over REST after the
same data was closed to it over MCP. The capability of a route now follows the
MCP classification, and the pairing is not a hand-written list: a route and a
read-only tool are paired when their handlers read the same source in the
package, found by parsing both.

Nothing here touches the screen, the mouse, the run-history database or the
USB ACL file: the two routes that would are replaced by recorders.
"""
import ast
import inspect
import json
import time
import re
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Set, Tuple

import pytest

from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.rbac import (
    USERS_ENV, Capability, Role, UserStore, capability_for_route, capability_for_tool,
)
from je_auto_control.utils.rbac.policy import DATA_ROUTES, REST_ROUTE_CAPABILITIES
from je_auto_control.utils.rest_api import rest_server
from je_auto_control.utils.rest_api.rest_openapi import build_openapi_spec
from je_auto_control.utils.rest_api.rest_server import RestApiServer

_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS out of scope

_READ, _DATA, _DRIVE = Capability.READ_SCREEN, Capability.READ_DATA, Capability.DRIVE_INPUT
_AUDIT, _HOSTS = Capability.READ_AUDIT, Capability.MANAGE_HOSTS

#: The whole table, written out: a change to any route has to be made here too.
_EXPECTED_ROUTES = {
    ("GET", "/metrics"): _READ,
    ("GET", "/jobs"): _READ,
    ("GET", "/history"): _DATA,
    ("GET", "/screenshot"): _READ,
    ("GET", "/mouse_position"): _READ,
    ("GET", "/screen_size"): _READ,
    ("GET", "/windows"): _READ,
    ("GET", "/sessions"): _READ,
    ("GET", "/commands"): _READ,
    ("GET", "/inspector/recent"): _READ,
    ("GET", "/inspector/summary"): _READ,
    ("GET", "/usb/devices"): _READ,
    ("GET", "/usb/events"): _READ,
    ("GET", "/usb/passthrough/status"): _READ,
    ("GET", "/usb/acl"): _DATA,
    ("GET", "/usb/loopback/devices"): _READ,
    ("GET", "/usb/remote/devices"): _READ,
    ("GET", "/diagnose"): _READ,
    ("GET", "/openapi.json"): _READ,
    ("GET", "/audit/list"): _AUDIT,
    ("GET", "/audit/verify"): _AUDIT,
    ("POST", "/execute"): _DRIVE,
    ("POST", "/execute_file"): _DRIVE,
    ("POST", "/usb/loopback/open"): _DRIVE,
    ("POST", "/usb/remote/open"): _DRIVE,
    ("POST", "/config/export"): _HOSTS,
    ("POST", "/config/import"): _HOSTS,
    ("POST", "/usb/passthrough/enable"): _HOSTS,
    ("POST", "/usb/acl/add"): _HOSTS,
    ("POST", "/usb/acl/remove"): _HOSTS,
    ("POST", "/usb/acl/default"): _HOSTS,
}


@pytest.fixture(autouse=True)
def _no_ambient_rbac(monkeypatch):
    """The developer's own environment must not switch RBAC on for these tests."""
    monkeypatch.delenv(USERS_ENV, raising=False)


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


@pytest.fixture
def rest(monkeypatch):
    """Start REST servers on ephemeral ports whose data routes only record the call."""
    served = []

    def recorder(name: str, payload: Dict[str, Any]) -> Callable[[Any], Tuple[int, Dict[str, Any]]]:
        def handle(_ctx):
            served.append(name)
            return 200, payload
        return handle

    monkeypatch.setitem(rest_server._GET_ROUTES, "/history",
                        recorder("/history", {"runs": [{"id": 7}]}))
    monkeypatch.setitem(rest_server._GET_ROUTES, "/usb/acl",
                        recorder("/usb/acl", {"default": "deny", "rules": []}))
    monkeypatch.setitem(rest_server._GET_ROUTES, "/jobs", recorder("/jobs", {"jobs": []}))
    started = []

    def start(**kwargs):
        server = RestApiServer(host="127.0.0.1", port=0, enable_audit=False, **kwargs)
        server._audit_log = _FakeAudit()
        server.start()
        server.served = served
        started.append(server)
        return server

    yield start
    for server in started:
        server.stop(timeout=10.0)


def _get(server, path: str, token: str):
    """``(status, decoded JSON)`` of one GET; an error status is returned, not raised."""
    host, port = server.address
    request = urllib.request.Request(
        f"{_SCHEME}://{host}:{port}{path}", method="GET",
        headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310  # reason: loopback test server
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def _wait_for_refusal(server, timeout_s: float = 5.0) -> bool:
    """Whether the audit log gets a READ_DATA refusal within ``timeout_s``.

    The handler thread writes the row after it has sent the reply, so the
    client can be back here first; that lost race failed this test on CI.
    """
    deadline = time.monotonic() + timeout_s
    wanted = f"forbidden:{Capability.READ_DATA}"
    while time.monotonic() < deadline:
        if any(wanted in json.dumps(row) for row in list(server._audit_log.rows)):
            return True
        time.sleep(0.01)
    return False


# --- what a role may read -----------------------------------------------------

@pytest.mark.parametrize("path", ["/history", "/usb/acl"])
def test_a_viewer_is_refused_a_stored_record_route(rest, users, path):
    server = rest(user_store=users)
    status, body = _get(server, path, users.tokens[Role.VIEWER])
    assert status == 403
    assert body == {"error": "forbidden", "role": Role.VIEWER,
                    "required_capability": Capability.READ_DATA}
    assert server.served == [], "the handler must not run for a refused caller"
    assert _wait_for_refusal(server), "the refusal is in the audit log with the capability it lacked"


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ADMIN])
@pytest.mark.parametrize("path", ["/history", "/usb/acl"])
def test_an_operator_and_an_admin_still_read_them(rest, users, role, path):
    server = rest(user_store=users)
    status, _body = _get(server, path, users.tokens[role])
    assert status == 200
    assert server.served == [path]


def test_a_viewer_keeps_the_routes_that_observe_live_state(rest, users):
    server = rest(user_store=users)
    viewer = users.tokens[Role.VIEWER]
    assert _get(server, "/jobs", viewer)[0] == 200
    assert _get(server, "/commands", viewer)[0] == 200
    assert _get(server, "/openapi.json", viewer)[0] == 200


def test_the_shared_token_is_not_restricted(rest):
    server = rest(token="shared-secret")
    assert _get(server, "/history", "shared-secret")[0] == 200
    assert _get(server, "/usb/acl", "shared-secret")[0] == 200
    assert server.served == ["/history", "/usb/acl"]


# --- the table ---------------------------------------------------------------

def test_the_route_table_is_the_one_documented():
    assert REST_ROUTE_CAPABILITIES == _EXPECTED_ROUTES
    assert DATA_ROUTES == {route for route, needed in _EXPECTED_ROUTES.items()
                           if needed == _DATA}
    for (method, path), needed in _EXPECTED_ROUTES.items():
        assert capability_for_route(method, path) == needed


def test_openapi_publishes_the_capability_of_the_data_routes():
    paths = build_openapi_spec()["paths"]
    assert paths["/history"]["get"]["x-required-capability"] == Capability.READ_DATA
    assert paths["/usb/acl"]["get"]["x-required-capability"] == Capability.READ_DATA
    assert paths["/jobs"]["get"]["x-required-capability"] == Capability.READ_SCREEN


# --- the same data needs the same capability on both surfaces -------------------
#
# A REST handler and an MCP tool handler are "the same data" when both read the
# same thing in the package: ``default_history_store.list_runs``,
# ``commands.acl_list`` ... Those are found by parsing each handler for what it
# uses of the names it imports from ``je_auto_control``, so a new route or tool
# is covered without being added to a list here.

Source = Tuple[str, str, str]

#: Imports every handler shares; reading the same logger is not reading the same data.
_PLUMBING = ("je_auto_control.utils.logging", "je_auto_control.utils.exception")


def _imported_names(nodes: Iterable[ast.AST]) -> Dict[str, Tuple[str, str]]:
    """``local name -> (module, imported name)`` for every ``from ... import`` below ``nodes``."""
    found: Dict[str, Tuple[str, str]] = {}
    for top in nodes:
        for node in ast.walk(top):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    found[alias.asname or alias.name] = (node.module, alias.name)
    return found


def _root_and_chain(node: ast.AST) -> Tuple[Optional[str], Tuple[str, ...]]:
    """``(name, attributes)`` of ``name.a.b`` / ``name().a``; the name is ``None`` otherwise."""
    chain = []
    while True:
        if isinstance(node, ast.Attribute):
            chain.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        else:
            break
    name = node.id if isinstance(node, ast.Name) else None
    return name, tuple(reversed(chain))


def _sources(function: Callable[..., Any]) -> Set[Source]:
    """What ``function`` reads from the package: ``(module, name, attribute path)``.

    Only the longest path per use is kept, so ``default_audit_log().query``
    is one source and does not also count as "anything from the audit log".
    """
    try:
        function = inspect.unwrap(function)
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        module_tree = ast.parse(inspect.getsource(inspect.getmodule(function)))
    except (OSError, TypeError, SyntaxError):
        return set()
    names = _imported_names(module_tree.body)
    names.update(_imported_names([tree]))
    uses: Set[Tuple[str, Tuple[str, ...]]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Name)):
            name, chain = _root_and_chain(node)
            if name in names and names[name][0].startswith("je_auto_control"):
                uses.add((name, chain))
    longest = {(name, chain) for name, chain in uses
               if not any(other_name == name and len(other) > len(chain)
                          and other[:len(chain)] == chain for other_name, other in uses)}
    return {(*names[name], ".".join(chain)) for name, chain in longest
            if not names[name][0].startswith(_PLUMBING)}


def _pairs() -> Dict[Tuple[str, str], Set[str]]:
    """``(method, path) -> names of the MCP tools reading a source that route reads``.

    Only ``GET`` routes and read-only tools are paired: a tool that lists
    windows and then focuses one reads what ``GET /windows`` reads without
    being the same operation, and the question here is who may *read*.
    """
    tools = build_default_tool_registry(read_only=False)
    tool_sources = {tool.name: _sources(tool.handler) for tool in tools}
    read_only = {tool.name: bool(tool.annotations.read_only) for tool in tools}
    paired: Dict[Tuple[str, str], Set[str]] = {}
    for path, handler in rest_server._GET_ROUTES.items():
        wanted = _sources(handler)
        paired[("GET", path)] = {name for name, sources in tool_sources.items()
                                 if read_only[name] and sources & wanted}
    return paired


#: Pairs the parser has to keep finding. Without this floor a refactor that
#: hides the shared source (a wrapper, a string lookup) would leave the test
#: comparing nothing and passing.
_KNOWN_PAIRS = {
    ("GET", "/history"): "ac_list_run_history",
    ("GET", "/usb/acl"): "ac_usb_acl_list",
    ("GET", "/jobs"): "ac_scheduler_list_jobs",
    ("GET", "/windows"): "ac_list_windows",
    ("GET", "/screen_size"): "ac_screen_size",
    ("GET", "/mouse_position"): "ac_get_mouse_position",
    ("GET", "/sessions"): "ac_remote_host_status",
    ("GET", "/usb/passthrough/status"): "ac_usb_passthrough_status",
    ("GET", "/usb/loopback/devices"): "ac_usb_loopback_list",
    ("GET", "/usb/remote/devices"): "ac_usb_remote_list",
}


def test_the_pairing_still_finds_the_routes_known_to_share_a_source():
    paired = _pairs()
    for route, tool in _KNOWN_PAIRS.items():
        assert tool in paired[route], f"{route} is no longer paired with {tool}"


def test_a_route_and_a_tool_serving_the_same_data_need_the_same_capability():
    disagreements = []
    for (method, path), tools in sorted(_pairs().items()):
        if path in rest_server._PUBLIC_PATHS:
            continue
        route_needs = capability_for_route(method, path)
        for tool in sorted(tools):
            tool_needs = capability_for_tool(tool, True)
            if tool_needs != route_needs:
                disagreements.append(
                    f"{method} {path} needs {route_needs}, {tool} needs {tool_needs}")
    assert disagreements == []


def test_the_parser_reads_a_source_passed_as_a_reference():
    """``_usb_command(commands.acl_list)`` hands the function over without calling it."""
    sources = _sources(rest_server._GET_ROUTES["/usb/acl"])
    assert ("je_auto_control.utils.usb.passthrough", "commands", "acl_list") in sources
    history = _sources(rest_server._GET_ROUTES["/history"])
    assert ("je_auto_control.utils.run_history.history_store",
            "default_history_store", "list_runs") in history
    assert not any(module.startswith(_PLUMBING) for module, _name, _path in history)


# --- the built-in dashboard ---------------------------------------------------

def _dashboard_script() -> str:
    path = Path(rest_server.__file__).parent / "dashboard" / "app.js"
    return path.read_text(encoding="utf-8")


def test_the_dashboard_calls_no_route_that_needs_read_data():
    """The page is read with whatever token is pasted in, a viewer's included."""
    fetched = {match.split("?")[0]
               for match in re.findall(r'fetchJson\("([^"]+)"\)', _dashboard_script())}
    assert fetched, "the script no longer fetches with a literal path this test can read"
    for path in fetched:
        assert ("GET", path) in REST_ROUTE_CAPABILITIES, path
    assert not {("GET", path) for path in fetched} & DATA_ROUTES
    needs = {path: capability_for_route("GET", path) for path in fetched}
    assert needs["/audit/list"] == Capability.READ_AUDIT, "the one panel a viewer is refused"
    assert {needed for path, needed in needs.items() if path != "/audit/list"} == {
        Capability.READ_SCREEN}


def test_the_dashboard_names_the_missing_capability_on_a_403():
    """Read from the source: there is no JavaScript runtime in the test environment."""
    script = _dashboard_script()
    assert "resp.status === 403" in script
    assert "required_capability" in script
    assert "not available to" in script
