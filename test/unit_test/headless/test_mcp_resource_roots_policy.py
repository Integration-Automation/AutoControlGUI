"""Resources and tools share per-connection realpath roots."""
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.resources import FileSystemProvider


def test_resources_use_all_client_roots_without_affecting_other_connections(tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir()
    b.mkdir()
    (a / 'one.json').write_text('{}')
    (b / 'two.json').write_text('{}')
    provider = FileSystemProvider(str(tmp_path))
    server = MCPServer(tools=[], resource_provider=provider)
    with server.connection_scope(connection_id='a'):
        server._apply_roots([{'uri': a.as_uri()}, {'uri': b.as_uri()}])
        listed = server._dispatch(1, 'resources/list', {})['resources']
        assert {r['name'] for r in listed} == {'one.json', 'two.json'}
    with server.connection_scope(connection_id='b'):
        server._apply_roots([{'uri': b.as_uri()}])
        listed = server._dispatch(1, 'resources/list', {})['resources']
        assert {r['name'] for r in listed} == {'two.json'}
    assert provider.root == str(tmp_path.resolve())


def test_configured_roots_bound_resources_before_client_initialize(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'safe.json').write_text('{}')
    monkeypatch.setenv('JE_AUTOCONTROL_MCP_ROOTS', str(root))
    server = MCPServer(tools=[], resource_provider=FileSystemProvider(str(tmp_path)))
    result = server._dispatch(1, 'resources/list', {})
    assert {r['name'] for r in result['resources']} == {'safe.json'}
