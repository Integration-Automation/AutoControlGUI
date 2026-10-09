"""MCP resources are gated by role like the tools that return the same data.

``resources/read`` was not checked against any capability: a viewer, who may
not call ``ac_list_run_history`` or ``ac_read_action_file``, read the same
rows at ``autocontrol://history`` and the same files under
``autocontrol://files/``.
"""
import json

import pytest

from je_auto_control.utils.mcp_server import _authz
from je_auto_control.utils.mcp_server.resources import MCPResource, ResourceProvider
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.policy import capability_for_tool
from je_auto_control.utils.rbac.users import Capability

_HISTORY = "autocontrol://history"
_FILE = "autocontrol://files/flow.json"
_COMMANDS = "autocontrol://commands"
_SCREEN = "autocontrol://screen/live"
_ALL = (_HISTORY, _FILE, _COMMANDS, _SCREEN)


class _Provider(ResourceProvider):
    """Every URI answers, and says which ones were read or subscribed to."""

    def __init__(self):
        self.read_uris, self.subscribed = [], []

    def list(self):
        return [MCPResource(uri=uri, name=uri, description="", mime_type="application/json")
                for uri in _ALL]

    def read(self, uri):
        self.read_uris.append(uri)
        return {"uri": uri, "mimeType": "application/json", "text": "{}"}

    def subscribe(self, uri, on_update):
        self.subscribed.append(uri)
        return object()

    def unsubscribe(self, uri, handle):
        """Nothing to release."""


@pytest.fixture
def provider():
    return _Provider()


def _ask(provider, method, params=None, role=None):
    server = MCPServer(tools=[], resource_provider=provider)
    message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    if role is None:
        return json.loads(server.handle_line(message))
    with authorization_scope(AuthorizationContext("someone", role)):
        return json.loads(server.handle_line(message))


@pytest.mark.parametrize("uri, capability", [
    (_HISTORY, Capability.READ_DATA), (_FILE, Capability.READ_DATA),
    (_COMMANDS, Capability.READ_SCREEN), (_SCREEN, Capability.READ_SCREEN),
    ("other://history", Capability.READ_DATA), ("other://commands", Capability.READ_SCREEN),
    ("autocontrol://something-new", Capability.READ_DATA), ("no-scheme", Capability.READ_DATA),
    ("autocontrol://screenshots/archive", Capability.READ_DATA),
])
def test_what_each_resource_needs(uri, capability):
    assert _authz.resource_capability(uri) == capability


def test_resources_need_what_the_tools_returning_the_same_data_need():
    assert _authz.resource_capability(_HISTORY) == capability_for_tool("ac_list_run_history", True)
    assert _authz.resource_capability(_FILE) == capability_for_tool("ac_read_action_file", True)
    assert _authz.resource_capability(_COMMANDS) == capability_for_tool("ac_list_action_commands", True)


@pytest.mark.parametrize("uri", [_HISTORY, _FILE])
def test_a_viewer_cannot_read_stored_records(provider, uri):
    answer = _ask(provider, "resources/read", {"uri": uri}, Role.VIEWER)
    assert answer["error"]["code"] == _authz.FORBIDDEN_CODE
    assert answer["error"]["data"] == {"required_capability": Capability.READ_DATA}
    assert provider.read_uris == [], "refused before the provider is asked"


@pytest.mark.parametrize("uri", [_COMMANDS, _SCREEN])
def test_a_viewer_still_reads_what_observes_the_host(provider, uri):
    answer = _ask(provider, "resources/read", {"uri": uri}, Role.VIEWER)
    assert answer["result"]["contents"][0]["uri"] == uri


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ADMIN])
@pytest.mark.parametrize("uri", _ALL)
def test_roles_with_read_data_read_everything(provider, role, uri):
    assert "result" in _ask(provider, "resources/read", {"uri": uri}, role)


@pytest.mark.parametrize("uri", _ALL)
def test_without_a_user_store_nothing_changes(provider, uri):
    assert "result" in _ask(provider, "resources/read", {"uri": uri})
    listed = _ask(provider, "resources/list")["result"]["resources"]
    assert [resource["uri"] for resource in listed] == list(_ALL)


def test_a_viewer_is_listed_only_what_it_may_read(provider):
    listed = _ask(provider, "resources/list", role=Role.VIEWER)["result"]["resources"]
    assert [resource["uri"] for resource in listed] == [_COMMANDS, _SCREEN]


def test_a_viewer_cannot_subscribe_to_what_it_cannot_read(provider):
    answer = _ask(provider, "resources/subscribe", {"uri": _HISTORY}, Role.VIEWER)
    assert answer["error"]["code"] == _authz.FORBIDDEN_CODE
    assert provider.subscribed == []
    assert "result" in _ask(provider, "resources/subscribe", {"uri": _SCREEN}, Role.VIEWER)
    assert provider.subscribed == [_SCREEN]


def test_a_refusal_is_recorded_in_the_audit_log(provider):
    records = []

    class _Audit:
        def record(self, **entry):
            records.append(entry)

    server = MCPServer(tools=[], resource_provider=provider)
    server._audit = _Audit()
    with authorization_scope(AuthorizationContext("vera", Role.VIEWER)):
        server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                                       "params": {"uri": _HISTORY}}))
    assert len(records) == 1
    assert records[0]["status"] == "denied"
    assert records[0]["arguments"] == {"uri": _HISTORY}
    assert records[0]["tool"] == "resources/read"
