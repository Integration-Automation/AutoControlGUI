"""Disclosure never grants native execution privileges or widens accepted request scopes."""
import json
import threading

import pytest

from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool
from je_auto_control.utils.mcp_server.tools._base import READ_ONLY, NON_DESTRUCTIVE
from je_auto_control.utils.mcp_server.tools._factories_discovery import discovery_tools
from je_auto_control.utils.mcp_server.tools._factories_disclosure import disclosure_tools
from je_auto_control.utils.rbac.authorization import AuthorizationContext


def _request(server, method, params=None):
    return json.loads(server.handle_line(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method,
                                                    'params': params or {}})))


def _server(tool, **kwargs):
    server = MCPServer(tools=[tool] + discovery_tools() + disclosure_tools(), **kwargs)
    server.configure_tool_disclosure('progressive')
    return server


def test_discovered_call_uses_existing_policy(tmp_path):
    executed = []
    root = tmp_path / 'root'
    root.mkdir()
    schema = {'type': 'object', 'properties': {'path': {'type': 'string', 'format': 'path'}},
              'required': ['path']}
    tool = MCPTool('ac_read_action_file', 'read', schema, lambda path: executed.append(path), READ_ONLY)
    audit = tmp_path / 'audit.jsonl'
    server = _server(tool, audit_logger=AuditLogger(str(audit)))
    with server.connection_scope(connection_id='viewer', authorization=AuthorizationContext('alice', 'admin')):
        server._apply_roots([{'uri': root.as_uri()}])
        found = _request(server, 'tools/call', {'name': 'ac_discover_tools', 'arguments': {'query': tool.name}})
        assert found['result']['structuredContent']['tools'][0]['name'] == tool.name
        _request(server, 'tools/call', {'name': 'ac_enable_tools', 'arguments': {'names': [tool.name]}})
        denied = _request(server, 'tools/call', {'name': tool.name, 'arguments': {'path': str(tmp_path / 'outside')}})
        assert denied['result']['isError']
        assert not executed
        allowed = _request(server, 'tools/call', {'name': tool.name, 'arguments': {'path': str(root / 'inside')}})
        assert not allowed['result']['isError']
        assert len(executed) == 1
    assert all(row['user_id'] == 'alice' for row in map(json.loads, audit.read_text().splitlines()))


def test_readonly_forbids_mutating_enable(monkeypatch):
    monkeypatch.setenv('JE_AUTOCONTROL_MCP_READONLY', '1')
    executed = []
    tool = MCPTool('ac_click_mouse', 'click', {'type': 'object'}, lambda: executed.append(True), NON_DESTRUCTIVE)
    server = _server(tool)
    with server.connection_scope(connection_id='readonly'):
        reply = _request(server, 'tools/call', {'name': 'ac_enable_tools', 'arguments': {'names': [tool.name]}})
        assert reply['result']['isError']
        assert tool.name not in server._disclosure.current().visible_names
        direct = _request(server, 'tools/call', {'name': tool.name})
        assert direct['result']['isError']
        assert executed == []


def test_removed_tool_cannot_run():
    executed = []
    tool = MCPTool('plugin', 'plugin', {'type': 'object'}, lambda: executed.append(True), READ_ONLY)
    server = _server(tool)
    with server.connection_scope(connection_id='old'):
        server._disclosure.current().enable([tool.name])
        assert server.unregister_tool(tool.name)
        reply = _request(server, 'tools/call', {'name': tool.name})
        assert reply['error']['code'] == -32602
        assert executed == []


def test_plain_client_static_profile():
    tool = MCPTool('fixed', 'fixed', {'type': 'object'}, lambda: None, READ_ONLY)
    server = MCPServer(tools=[tool] + discovery_tools() + disclosure_tools())
    server.configure_tool_disclosure('static', profile=['fixed'])
    with server.connection_scope(connection_id='plain'):
        reply = _request(server, 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                                'clientInfo': {'name': 'plain', 'version': '1'}})
        assert not reply['result']['capabilities']['tools']['listChanged']
        assert 'fixed' in {item['name'] for item in _request(server, 'tools/list')['result']['tools']}
        assert _request(server, 'tools/call', {'name': 'ac_disable_tools',
                                             'arguments': {'names': ['fixed']}})['result']['isError']


def test_async_call_retains_client_root_and_identity(tmp_path, monkeypatch):
    executed, replies = [], []
    entered, release = threading.Event(), threading.Event()
    root = tmp_path / 'root'
    root.mkdir()
    schema = {'type': 'object', 'properties': {'path': {'type': 'string', 'format': 'path'}}}
    tool = MCPTool('ac_read_action_file', 'read', schema, lambda path: executed.append(path), READ_ONLY)
    server = _server(tool, concurrent_tools=True)
    original = server._build_response
    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(server, '_build_response', delayed)
    try:
        with server.connection_scope(connection_id='peer', writer=replies.append, concurrent_tools=True,
                                     authorization=AuthorizationContext('alice', 'admin')):
            server._apply_roots([{'uri': root.as_uri()}])
            assert server.handle_line(json.dumps({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
                'params': {'name': tool.name, 'arguments': {'path': str(tmp_path / 'outside')}}})) is None
        assert entered.wait(5)
        server.forget_connection('peer')
    finally:
        release.set()
        server._join_workers()
    assert len(replies) == 1
    assert json.loads(replies[0])['result']['isError']
    assert executed == []
    assert server._disclosure.view_count == 0


def test_cli_disclosure_flags(monkeypatch):
    from je_auto_control.utils.mcp_server import __main__ as cli
    calls = []
    monkeypatch.setattr(cli, 'start_mcp_stdio_server', lambda **kwargs: calls.append(kwargs))
    cli.main(['--tool-mode', 'static', '--tool-profile', 'ac_screenshot,ac_probe_capabilities',
              '--tool-page-size', '2'])
    assert calls == [{'read_only': None, 'tool_mode': 'static',
                     'tool_profile': ('ac_screenshot', 'ac_probe_capabilities'), 'tool_page_size': 2}]
    with pytest.raises(SystemExit):
        cli.main(['--tool-page-size', '0'])
