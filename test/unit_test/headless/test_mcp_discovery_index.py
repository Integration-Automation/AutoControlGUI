"""Registry-only MCP discovery snapshots, policy filtering and bounded single schemas."""
import json

import pytest

from je_auto_control.utils.mcp_server.tools import MCPTool
from je_auto_control.utils.mcp_server.tools._base import READ_ONLY
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


def _tools():
    return [MCPTool('ac_screenshot', 'Capture screen pixels', {'type': 'object'}, lambda: None, READ_ONLY),
            MCPTool('private_admin', 'Manage secrets', {'type': 'object'}, lambda: None)]


def test_search_returns_summary_not_full_schema():
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    results = ToolIndex(_tools(), version=12).search('screen')
    assert results[0].name == 'ac_screenshot'
    assert 'inputSchema' not in results[0].to_dict()
    assert results[0].to_dict()['required_capability'] == 'read_screen'


def test_only_authorized_tools_are_indexed():
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    index = ToolIndex(_tools())
    with authorization_scope(AuthorizationContext('v', 'viewer')):
        assert [row.name for row in index.search('')] == ['ac_screenshot']
        with pytest.raises(ValueError, match='unavailable'):
            index.get_schema('private_admin')


def test_schema_lookup_is_single_tool():
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    tools = _tools()
    index = ToolIndex(tools, version=9)
    tools[0].input_schema['mutated'] = True
    reply = index.get_schema('ac_screenshot')
    assert reply.name == 'ac_screenshot'
    assert index.version == 9
    assert 'mutated' not in reply.to_dict()['inputSchema']
    exported = reply.to_dict()
    exported['inputSchema']['mutated'] = True
    assert 'mutated' not in index.get_schema('ac_screenshot').to_dict()['inputSchema']


@pytest.mark.parametrize('query,limit', [('x', 0), ('x', 101), ('x', True), ('x', 1.5), ('x' * 513, 10)])
def test_search_rejects_unbounded_input(query, limit):
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    with pytest.raises(ValueError):
        ToolIndex(_tools()).search(query, limit=limit)


def test_readonly_filters_summary_and_schema(monkeypatch):
    from je_auto_control.utils.mcp_server.discovery import ToolIndex
    monkeypatch.setenv('JE_AUTOCONTROL_MCP_READONLY', '1')
    index = ToolIndex(_tools())
    assert [row.name for row in index.search('')] == ['ac_screenshot']
    with pytest.raises(ValueError, match='unavailable'):
        index.get_schema('private_admin')


def test_server_discovery_uses_live_registry_and_removed_plugin():
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.tools._factories_discovery import discovery_tools
    server = MCPServer(tools=_tools() + discovery_tools())
    def call(name, arguments):
        return json.loads(server.handle_line(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                                       'params': {'name': name, 'arguments': arguments}})))
    reply = call('ac_discover_tools', {'query': 'screen'})
    assert reply['result']['structuredContent']['tools'][0]['name'] == 'ac_screenshot'
    old = reply['result']['structuredContent']['version']
    assert server.unregister_tool('ac_screenshot')
    reply = call('ac_discover_tools', {'query': 'screen'})
    assert not reply['result']['structuredContent']['tools']
    assert reply['result']['structuredContent']['version'] > old
    schema = call('ac_get_tool_schema', {'name': 'ac_screenshot'})
    assert schema['result']['isError']


def test_facade_executor_and_builder_share_discovery():
    import je_auto_control as ac
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert ac.discover_tools('discover_tools')['tools'][0]['name'] == 'ac_discover_tools'
    assert ac.get_tool_schema('ac_discover_tools')['name'] == 'ac_discover_tools'
    assert executor.event_dict['AC_get_tool_schema']('ac_discover_tools')['name'] == 'ac_discover_tools'
    specs = _build_specs()
    assert {'AC_discover_tools', 'AC_get_tool_schema'} <= {spec.command for spec in specs}


def test_gui_discovery_actions_are_async_and_close_revokes():
    import os
    import subprocess
    import sys
    pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
    result = subprocess.run([sys.executable, '-c', """
import time
from PySide6.QtWidgets import QApplication,QMenu
from je_auto_control.gui.mcp_discovery_dialog import MCPDiscoveryDialog
app=QApplication([]);dialog=MCPDiscoveryDialog()
menu=dialog.findChild(QMenu)
assert len(menu.actions())==3
dialog.query.setText('discover_tools');dialog.search()
deadline=time.monotonic()+5
while dialog._tasks.handle is not None and time.monotonic()<deadline:
 app.processEvents();time.sleep(.005)
assert 'ac_discover_tools' in dialog.output.toPlainText()
assert 'inputSchema' not in dialog.output.toPlainText()
dialog.name.setText('ac_discover_tools');dialog.read_schema()
while dialog._tasks.handle is not None and time.monotonic()<deadline:
 app.processEvents();time.sleep(.005)
assert 'inputSchema' in dialog.output.toPlainText()
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
language_wrapper.reset_language('Traditional_Chinese')
assert dialog.query.text()=='discover_tools'
assert 'MCP' in dialog.windowTitle() and '探索' in dialog.windowTitle()
dialog.reject();dialog.close();app.processEvents()
"""], capture_output=True, text=True, timeout=30, env=dict(os.environ, QT_QPA_PLATFORM='offscreen'))
    assert result.returncode == 0, result.stderr
