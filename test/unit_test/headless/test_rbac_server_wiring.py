"""Authenticated identities govern REST/MCP execution, discovery and audit."""
import http.client
import json
from types import SimpleNamespace

import pytest

from je_auto_control.utils.rbac import Role, UserStore
from je_auto_control.utils.rest_api import rest_server
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.http_transport import HttpMCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, MCPToolAnnotations
from je_auto_control.utils.mcp_server.audit import AuditLogger


@pytest.fixture
def users(tmp_path, monkeypatch):
    store = UserStore(tmp_path / 'users.json')
    for role in (Role.VIEWER, Role.OPERATOR, Role.ADMIN):
        store.add_user(user_id=role, display_name=role, role=role, token=f'{role}-token')
    monkeypatch.setenv('JE_AUTOCONTROL_USERS', str(store.path))
    return store


def _request(address, token, path, body=None):
    connection = http.client.HTTPConnection(*address, timeout=5)
    encoded = json.dumps(body) if body is not None else None
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    try:
        connection.request('POST' if body is not None else 'GET', path, encoded, headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


@pytest.fixture
def rest(users, monkeypatch):
    calls, audit = [], []
    monkeypatch.setitem(rest_server._POST_ROUTES, '/execute',
                        lambda ctx: (calls.append(ctx.body) or 200, {'executed': True}))
    server = rest_server.RestApiServer(port=0, token='shared-token', enable_audit=False)
    server._audit_log = SimpleNamespace(log=lambda *args, **kwargs: audit.append(kwargs),
                                       query=lambda **kwargs: [])
    server.start()
    try:
        yield server, calls, audit
    finally:
        server.stop()


def test_viewer_cannot_execute(rest):
    server, calls, _audit = rest
    status, _ = _request(server.address, 'viewer-token', '/execute', {'actions': []})
    assert status == 403
    assert calls == []


def test_operator_can_execute_without_shared_token(rest):
    server, calls, _audit = rest
    status, _ = _request(server.address, 'operator-token', '/execute', {'actions': []})
    assert status == 200
    assert len(calls) == 1


def test_configured_empty_store_does_not_fall_back(rest, users):
    server, calls, _audit = rest
    status, _ = _request(server.address, 'shared-token', '/execute', {'actions': []})
    assert status == 401
    assert calls == []


def test_user_id_in_audit(rest):
    server, _calls, audit = rest
    assert _request(server.address, 'operator-token', '/execute', {'actions': []})[0] == 200
    assert audit[-1]['user_id'] == 'operator'


@pytest.fixture
def mcp(users, tmp_path):
    called = []
    tools = [
        MCPTool('ac_sign_actions', 'sign', {'type': 'object'}, lambda: called.append('sign')),
        MCPTool('ac_click_mouse', 'input', {'type': 'object'}, lambda: called.append('click')),
        MCPTool('ac_get_mouse_position', 'read', {'type': 'object'}, lambda: [1, 2],
                annotations=MCPToolAnnotations(read_only=True)),
    ]
    audit_path = tmp_path / 'audit.jsonl'
    bridge = MCPServer(tools=tools, audit_logger=AuditLogger(str(audit_path)))
    server = HttpMCPServer(bridge, port=0, auth_token='shared-token')
    server.start()
    try:
        yield server, called, audit_path
    finally:
        server.stop()


def _mcp(server, token, method, params=None):
    return _request(server.address, token, '/mcp',
                    {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})


def test_operator_cannot_sign(mcp):
    server, called, _audit = mcp
    status, body = _mcp(server, 'operator-token', 'tools/call', {'name': 'ac_sign_actions'})
    assert status == 200
    assert body['result']['isError'] is True
    assert called == []


def test_mcp_discovery_matches_permissions(mcp):
    server, _called, _audit = mcp
    _, body = _mcp(server, 'viewer-token', 'tools/list')
    assert [tool['name'] for tool in body['result']['tools']] == ['ac_get_mouse_position']
    _, body = _mcp(server, 'operator-token', 'tools/list')
    assert {tool['name'] for tool in body['result']['tools']} == {'ac_get_mouse_position', 'ac_click_mouse'}


def test_mcp_audit_has_user_id_and_denials(mcp):
    server, called, audit = mcp
    assert _mcp(server, 'admin-token', 'tools/call', {'name': 'ac_sign_actions'})[0] == 200
    assert _mcp(server, 'viewer-token', 'tools/call', {'name': 'ac_click_mouse'})[0] == 200
    records = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines()]
    assert [(row['user_id'], row['status']) for row in records] == [('admin', 'ok'), ('viewer', 'denied')]
    assert called == ['sign']


def test_unconfigured_rbac_keeps_shared_token(monkeypatch):
    monkeypatch.delenv('JE_AUTOCONTROL_USERS', raising=False)
    server = rest_server.RestApiServer(port=0, token='shared-token', enable_audit=False)
    server.start()
    try:
        assert _request(server.address, 'shared-token', '/screen_size')[0] == 200
        assert _request(server.address, 'wrong-token', '/screen_size')[0] == 401
    finally:
        server.stop()


@pytest.mark.parametrize('role, command', [('operator', 'AC_sign_actions'),
                                          ('viewer', 'AC_click_mouse')])
def test_nested_commands_cannot_bypass_role_checks(monkeypatch, role, command):
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
    called = []
    executor = Executor()
    monkeypatch.setitem(executor.event_dict, command, lambda: called.append(command))
    with authorization_scope(AuthorizationContext(role, role)):
        with pytest.raises(AuthorizationError):
            executor._execute_event([command, {}])
    assert called == []


def test_rest_audit_user_id_survives_hash_chain(tmp_path):
    from je_auto_control.utils.remote_desktop.audit_log import AuditLog
    log = AuditLog(tmp_path / 'audit.db')
    log.log('rest_api', user_id='operator', detail='POST /execute -> ok:200')
    assert log.query()[0]['user_id'] == 'operator'
    assert log.verify_chain().ok is True
    log.close()


def _raw(server, token, method, body=None, session=None):
    connection = http.client.HTTPConnection(*server.address, timeout=5)
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    if session:
        headers['Mcp-Session-Id'] = session
    if method == 'GET':
        headers['Accept'] = 'text/event-stream'
    try:
        connection.request(method, '/mcp', json.dumps(body) if body else None, headers)
        response = connection.getresponse()
        return response.status, response.getheader('Mcp-Session-Id')
    finally:
        connection.close()


@pytest.mark.parametrize('method', ['POST', 'GET', 'DELETE'])
def test_mcp_sessions_belong_to_authenticated_user(mcp, method):
    server, _called, _audit = mcp
    status, session = _raw(server, 'admin-token', 'POST',
                          {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}})
    assert status == 200 and session
    body = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'} if method == 'POST' else None
    assert _raw(server, 'viewer-token', method, body, session)[0] == 404


def test_metrics_require_audit_capability(rest):
    server, _called, _audit = rest
    connection = http.client.HTTPConnection(*server.address, timeout=5)
    try:
        connection.request('GET', '/metrics', headers={'Authorization': 'Bearer viewer-token'})
        assert connection.getresponse().status == 403
    finally:
        connection.close()


def test_empty_configured_users_rejects_the_legacy_token(tmp_path, monkeypatch):
    monkeypatch.setenv('JE_AUTOCONTROL_USERS', str(tmp_path / 'empty-users.json'))
    server = rest_server.RestApiServer(port=0, token='shared-token', enable_audit=False)
    server.start()
    try:
        assert _request(server.address, 'shared-token', '/screen_size')[0] == 401
    finally:
        server.stop()


@pytest.mark.parametrize('command', ['AC_execute_process', 'AC_android_shell',
                                    'AC_add_package_to_callback_executor', 'AC_parallel',
                                    'AC_run_dag', 'AC_load_dotenv', 'AC_lease_secret',
                                    'AC_scan_secrets', 'AC_email_trigger_add', 'AC_watchdog_start'])
def test_deferred_and_host_operations_are_admin_only(command):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope, permitted
    with authorization_scope(AuthorizationContext('operator', 'operator')):
        assert permitted(command, read_only=True) is False


def test_user_management_delivery_surfaces():
    import je_auto_control as ac
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    commands = {'AC_user_add', 'AC_user_list', 'AC_user_remove', 'AC_user_set_role', 'AC_user_rotate_token'}
    assert commands <= executor.known_commands()
    assert {name.lower() for name in commands} <= {tool.name for tool in build_default_tool_registry()}
    assert commands <= {spec.command for spec in _build_specs()}
    assert all(hasattr(ac, name) for name in ('UserStore', 'AuthorizationContext', 'rbac_add_user'))


def test_user_management_reuses_configured_store_and_hides_tokens(users):
    from je_auto_control.utils.rbac.user_api import rbac_add_user, rbac_list_users, rbac_set_role, rbac_remove_user
    from je_auto_control.utils.rbac.authorization import configured_user_store
    rbac_add_user('alice', 'Alice', 'viewer', 'alice-token')
    store = configured_user_store()
    assert store.authenticate('alice-token').role == 'viewer'
    rbac_set_role('alice', 'operator')
    assert store.authenticate('alice-token').role == 'operator'
    assert 'token' not in json.dumps(rbac_list_users())
    assert rbac_remove_user('alice')['removed'] is True


def test_admin_gui_uses_the_server_store(users, monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui._user_admin_panel import UserAdminPanel
    from je_auto_control.utils.rest_api.rest_auth import RestAuthGate
    app = QApplication.instance() or QApplication([])
    panel = UserAdminPanel()
    assert panel.store is RestAuthGate('legacy').user_store
    assert len(panel.menu_actions()) == 5
    panel.close()
    assert app is not None


def test_rotate_can_install_a_supplied_token(users):
    assert users.rotate_token('viewer', token='replacement-token') == 'replacement-token'
    assert users.authenticate('replacement-token').user_id == 'viewer'


@pytest.mark.parametrize('command', ['AC_add_package_to_executor', 'AC_load_plugins',
                                    'AC_run_agent', 'AC_admin_broadcast_execute',
                                    'AC_start_mcp_server', 'AC_start_remote_host',
                                    'AC_start_ws_host', 'AC_stop_remote_host',
                                    'AC_web_run_actions', 'AC_http_request',
                                    'AC_s3_upload', 'AC_write_document',
                                    'AC_element_save', 'AC_skill_save', 'AC_notify_webhook'])
def test_indirect_host_operations_cannot_bypass_role(command):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope, permitted
    with authorization_scope(AuthorizationContext('operator', 'operator')):
        assert permitted(command, read_only=True) is False


def test_async_mcp_preserves_authorization_and_audit(tmp_path):
    import threading
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, current_authorization
    identities, replies = [], []
    done = threading.Event()
    tool = MCPTool('ac_get_mouse_position', 'read', {'type': 'object'},
                   lambda: identities.append(current_authorization().user_id),
                   annotations=MCPToolAnnotations(read_only=True))
    path = tmp_path / 'async-audit.jsonl'
    server = MCPServer(tools=[tool], audit_logger=AuditLogger(str(path)))
    def writer(payload):
        replies.append(json.loads(payload))
        done.set()
    with server.connection_scope(writer=writer, authorization=AuthorizationContext('alice', 'viewer')):
        server._dispatch_tools_call_async(1, {'name': tool.name})
    assert done.wait(5)
    assert replies[0]['result']['isError'] is False
    assert identities == ['alice']
    assert json.loads(path.read_text())['user_id'] == 'alice'
    assert current_authorization() is None


def test_user_api_role_denial_and_result_redaction(users):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
    from je_auto_control.utils.rbac.user_api import rbac_add_user, rbac_rotate_token
    with authorization_scope(AuthorizationContext('operator', 'operator')):
        with pytest.raises(AuthorizationError):
            rbac_add_user('denied', 'Denied', 'admin', 'secret')
    assert users.get('denied') is None
    result = rbac_rotate_token('viewer', 'new-secret')
    assert 'new-secret' not in json.dumps(result) and 'token_hash' not in result


def test_rotating_to_another_users_token_does_not_change_store(users):
    from je_auto_control.utils.rbac.users import UserAuthError
    with pytest.raises(UserAuthError):
        users.rotate_token('viewer', token='admin-token')
    assert users.authenticate('viewer-token').user_id == 'viewer'
    assert users.authenticate('admin-token').user_id == 'admin'


@pytest.mark.parametrize('uri', ['autocontrol://history', 'autocontrol://files/secret.json'])
def test_viewer_cannot_discover_or_read_privileged_resources(uri, tmp_path):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext
    from je_auto_control.utils.mcp_server.resources import default_resource_provider
    (tmp_path / 'secret.json').write_text('[]')
    server = MCPServer(tools=[], resource_provider=default_resource_provider(str(tmp_path)))
    with server.connection_scope(authorization=AuthorizationContext('viewer', 'viewer')):
        listed = server._handle_resources_list()['resources']
        assert uri not in {r['uri'] for r in listed}
        response = json.loads(server.handle_line(json.dumps(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'resources/read', 'params': {'uri': uri}})))
        assert 'error' in response



@pytest.mark.parametrize('operation', ['add', 'rotate'])
def test_command_adapters_reject_empty_supplied_tokens(users, operation):
    from je_auto_control.utils.rbac.user_api import rbac_add_user, rbac_rotate_token
    from je_auto_control.utils.rbac.users import UserAuthError
    with pytest.raises(UserAuthError):
        if operation == 'add':
            rbac_add_user('new', 'New', 'viewer', '')
        else:
            rbac_rotate_token('viewer', '')
    assert users.get('new') is None
    assert users.authenticate('viewer-token').user_id == 'viewer'


def test_viewer_cannot_enable_audit_logging(monkeypatch):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext
    server = MCPServer(tools=[])
    calls = []
    monkeypatch.setattr(server, '_handle_logging_set_level', lambda params: calls.append(params) or {})
    with server.connection_scope(authorization=AuthorizationContext('viewer', 'viewer')):
        response = json.loads(server.handle_line(json.dumps(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'logging/setLevel', 'params': {'level': 'debug'}})))
    assert 'error' in response
    assert calls == []
