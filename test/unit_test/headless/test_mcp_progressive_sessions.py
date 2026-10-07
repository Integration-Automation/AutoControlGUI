"""Owned progressive tool views, coherent cursors and unchanged full-mode descriptors."""
from dataclasses import replace

import pytest

from je_auto_control.utils.mcp_server.discovery import ToolIndex
from je_auto_control.utils.mcp_server.tools import MCPTool
from je_auto_control.utils.mcp_server.tools._base import READ_ONLY


def _registry():
    return [MCPTool(name, name, {'type': 'object'}, lambda: None, READ_ONLY)
            for name in ('ac_discover_tools', 'ac_enable_tools', 'ac_tool_state', 'one', 'two', 'three')]


def test_enable_is_session_local():
    from je_auto_control.utils.mcp_server.disclosure import ToolView
    index = ToolIndex(_registry())
    first, second = ToolView(lambda: index), ToolView(lambda: index)
    assert first.enable(['one']).changed
    assert 'one' in first.visible_names
    assert 'one' not in second.visible_names


def test_cursor_snapshot_survives_plugin_change():
    from je_auto_control.utils.mcp_server.disclosure import ToolView
    registry = _registry()
    index = ToolIndex(registry, version=1)
    view = ToolView(lambda: index, mode='full', page_size=2)
    page = view.list_page()
    assert page.next_cursor
    index = ToolIndex([replace(tool, description='changed') for tool in registry], version=2)
    next_page = view.list_page(page.next_cursor)
    assert next_page.snapshot_id == page.snapshot_id
    assert next_page.version == 1
    assert all(tool.to_dict()['description'] != 'changed' for tool in next_page.tools)
    with pytest.raises(ValueError, match='cursor'):
        view.list_page('other-view-cursor')


def test_enable_emits_list_changed():
    from je_auto_control.utils.mcp_server.disclosure import ToolView
    events = []
    index = ToolIndex(_registry())
    view = ToolView(lambda: index, notify=lambda: events.append('changed'))
    assert view.enable(['one']).changed
    assert not view.enable(['one', 'one']).changed
    assert not view.enable(['ac_discover_tools']).changed
    assert events == ['changed']
    assert view.disable(['one']).changed
    assert events == ['changed', 'changed']


def test_full_mode_is_compatible():
    from je_auto_control.utils.mcp_server.disclosure import ToolView
    index = ToolIndex(_registry())
    view = ToolView(lambda: index, mode='full', page_size=100)
    assert view.visible_names == tuple(tool.name for tool in _registry())
    assert {tool.name for tool in view.list_page().tools} == {tool.name for tool in _registry()}


def test_static_profile_does_not_change_and_closed_views_reclaim():
    from je_auto_control.utils.mcp_server.disclosure import ToolView
    index = ToolIndex(_registry())
    view = ToolView(lambda: index, mode='static', profile=['two'], page_size=1)
    page = view.list_page()
    assert 'two' in view.visible_names and 'one' not in view.visible_names
    with pytest.raises(ValueError, match='static'):
        view.enable(['one'])
    view.close()
    assert view.snapshot_count == 0
    with pytest.raises(ValueError, match='closed'):
        view.list_page(page.next_cursor)


def test_cursors_are_foreign_expired_and_permission_safe(monkeypatch):
    from je_auto_control.utils.mcp_server import disclosure
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
    index = ToolIndex(_registry()[3:])
    first = disclosure.ToolView(lambda: index, mode='full', page_size=1)
    second = disclosure.ToolView(lambda: index, mode='full', page_size=1)
    cursor = first.list_page().next_cursor
    with pytest.raises(ValueError, match='cursor'):
        second.list_page(cursor)
    # Viewer cannot read unknown/admin tools from an index created while unrestricted.
    with authorization_scope(AuthorizationContext('viewer', 'viewer')):
        with pytest.raises(ValueError, match='permissions'):
            first.list_page(cursor)
    monkeypatch.setattr(disclosure.time, 'monotonic', lambda: 10**12)
    with pytest.raises(ValueError, match='stale'):
        first.list_page(cursor)
    assert first.snapshot_count == 0


def test_transport_scopes_enable_and_cleanup():
    import json
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.tools._factories_discovery import discovery_tools
    from je_auto_control.utils.mcp_server.tools._factories_disclosure import disclosure_tools
    server = MCPServer(tools=_registry()[3:] + discovery_tools() + disclosure_tools())
    server.configure_tool_disclosure('progressive')
    def request(method, params):
        return json.loads(server.handle_line(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method,
                                                        'params': params})))['result']
    first_events, second_events = [], []
    with server.connection_scope(connection_id='first', notifier=lambda *args: first_events.append(args)):
        initial = request('tools/list', {})
        assert 'one' not in {tool['name'] for tool in initial['tools']}
        reply = request('tools/call', {'name': 'ac_enable_tools', 'arguments': {'names': ['one']}})
        assert reply['structuredContent']['changed']
        assert 'one' in {tool['name'] for tool in request('tools/list', {})['tools']}
    with server.connection_scope(connection_id='second', notifier=lambda *args: second_events.append(args)):
        assert 'one' not in {tool['name'] for tool in request('tools/list', {})['tools']}
    assert len(first_events) == 1 and not second_events
    server.forget_connection('first')
    server.forget_connection('second')
    assert server._disclosure.view_count == 0


def test_default_full_transport_shape_is_unchanged():
    import json
    from je_auto_control.utils.mcp_server.server import MCPServer
    server = MCPServer(tools=_registry())
    response = json.loads(server.handle_line(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})))
    assert response['result'] == {'tools': [tool.to_descriptor() for tool in _registry()]}


def test_preview_surfaces_are_isolated_and_owned_scope_stays_closed():
    import je_auto_control as ac
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server._disclosure_sessions import ToolSessions
    index = ToolIndex(_registry())
    sessions = ToolSessions(lambda: index, lambda key: None)
    sessions.configure('progressive')
    with sessions.scope('owned'):
        view = sessions.current()
        assert view.enable(['one']).changed
        sessions.forget('owned')
        assert sessions.current() is view
        with pytest.raises(ValueError, match='closed'):
            sessions.current().enable(['two'])
    assert sessions.view_count == 0
    preview = ac.preview_tool_disclosure(names=['ac_screenshot'])
    assert 'ac_screenshot' in preview['names']
    assert 'nextCursor' not in preview
    action = executor.event_dict['AC_preview_tool_disclosure'](names='["ac_screenshot"]')
    assert action['names'] == preview['names']


@pytest.mark.parametrize('cursor', [None, False, 1, '', 'x' * 513])
def test_wire_cursor_rejects_invalid_values(cursor):
    import json
    from je_auto_control.utils.mcp_server.server import MCPServer
    server = MCPServer(tools=_registry())
    response = json.loads(server.handle_line(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list',
                                                       'params': {'cursor': cursor}})))
    assert response['error']['code'] == -32602


def test_snapshot_cache_bound_and_standing_stream_notification():
    import json
    from je_auto_control.utils.mcp_server import disclosure
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.http_sessions import SessionRegistry
    index = ToolIndex(_registry())
    view = disclosure.ToolView(lambda: index, mode='full', page_size=1)
    old = view.list_page().next_cursor
    for _ in range(disclosure.MAX_SNAPSHOTS):
        view.list_page()
    assert view.snapshot_count == disclosure.MAX_SNAPSHOTS
    with pytest.raises(ValueError, match='stale'):
        view.list_page(old)
    server = MCPServer(tools=_registry())
    registry = SessionRegistry(on_drop=lambda session: server.forget_connection(session.id))
    session = registry.create()
    lines = []
    assert session.attach_stream(lines.append)
    def lookup(key):
        writer = registry.stream_writer_for(key)
        return (lambda method, params: writer(json.dumps({'method': method, 'params': params}))) if writer else None
    server._disclosure.set_notifier_lookup(lookup)
    with server.connection_scope(connection_id=session.id):
        pass
    server.register_tool(MCPTool('new_plugin', 'new plugin', {}, lambda: None))
    assert json.loads(lines[-1])['method'] == 'notifications/tools/list_changed'
    registry.terminate(session.id)
    assert registry.stream_writer_for(session.id) is None
    assert server._disclosure.view_count == 0


def test_removed_names_can_be_disabled_and_selection_is_bounded(monkeypatch):
    from je_auto_control.utils.mcp_server import disclosure
    index = ToolIndex(_registry())
    view = disclosure.ToolView(lambda: index)
    assert view.enable(['one']).changed
    index = ToolIndex(_registry()[:3])
    assert view.disable(['one']).changed
    assert not view.disable(['one']).changed
    index = ToolIndex(_registry())
    monkeypatch.setattr(disclosure, 'MAX_SELECTED_TOOLS', 1)
    assert view.enable(['one']).changed
    with pytest.raises(ValueError, match='selection'):
        view.enable(['two'])
    assert 'two' not in view.visible_names


def test_static_and_stateless_capabilities_match_fixed_availability():
    import json
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server._stateless import META_PROTOCOL_VERSION, STATELESS_PROTOCOL_VERSION
    server = MCPServer(tools=_registry())
    server.configure_tool_disclosure('static', profile=['one'])
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
               'params': {'protocolVersion': '2025-11-25', 'capabilities': {}}}
    response = json.loads(server.handle_line(json.dumps(request)))['result']
    assert not response['capabilities']['tools']['listChanged']
    request['method'] = 'server/discover'
    request['params'] = {'_meta': {META_PROTOCOL_VERSION: STATELESS_PROTOCOL_VERSION,
                                  'io.modelcontextprotocol/clientInfo': {'name': 'test', 'version': '1'},
                                  'io.modelcontextprotocol/clientCapabilities': {}}}
    response = json.loads(server.handle_line(json.dumps(request)))['result']
    assert not response['capabilities']['tools']['listChanged']
