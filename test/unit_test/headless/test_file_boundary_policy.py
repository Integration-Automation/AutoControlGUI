"""Filesystem semantics and reference policies at MCP/viewer boundaries."""
import json
import os
import subprocess

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.remote_desktop.file_transfer import (
    FileReceiver, encode_begin, encode_chunk, encode_end, new_transfer_id,
)
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer


def _call(server, name, arguments):
    return server._handle_tools_call(1, {'name': name, 'arguments': arguments})


def test_semantic_path_fields_only(tmp_path, monkeypatch):
    monkeypatch.setenv('JE_AUTOCONTROL_MCP_ROOTS', str(tmp_path))
    tools = {t.name: t for t in build_default_tool_registry(aliases=False)}
    assert tools['ac_read_document'].input_schema['properties']['path']['format'] == 'path'
    assert 'format' not in tools['ac_json_query'].input_schema['properties']['path']
    assert 'format' not in tools['ac_generate_sbom'].input_schema['properties']['root']
    server = MCPServer()
    result = _call(server, 'ac_json_query', {'data': {'value': 3}, 'path': '$.value'})
    assert result['isError'] is False
    outside = tmp_path.parent / 'outside.env'
    outside.write_text('SENSITIVE=do-not-disclose', encoding='utf-8')
    denied = _call(server, 'ac_load_dotenv', {'path': str(outside)})
    assert denied['isError'] is True
    assert 'do-not-disclose' not in json.dumps(denied)


def test_symlink_escape_is_rejected(tmp_path):
    from je_auto_control.utils.path_guard.policy import PathPolicy
    root = tmp_path / 'root'
    outside = tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    try:
        (root / 'link').symlink_to(outside, target_is_directory=True)
    except OSError as error:
        if os.name != 'nt' or error.winerror != 1314:
            raise
        # Directory junctions exercise realpath escapes without requiring
        # Windows' symlink privilege or developer mode.
        subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(root / 'link'), str(outside)],
                       check=True, capture_output=True)
    policy = PathPolicy(roots=[root])
    with pytest.raises(AutoControlException):
        policy.validate(str(root / 'link' / 'new-file'), operation='write')


@pytest.mark.parametrize('destination', ['../escape.bin', '/tmp/escape.bin',
    'C:\\escape.bin', 'C:escape.bin', '\\\\server\\share\\escape.bin',
    '..\\escape.bin', '~/.ssh/authorized_keys', 'x.bin:stream'])
def test_viewer_file_rejects_escaping_destinations(tmp_path, destination):
    root = tmp_path / 'downloads'
    completes = []
    receiver = FileReceiver(base_dir=root, on_complete=lambda *args: completes.append(args))
    receiver.handle_begin(encode_begin(new_transfer_id(), destination, 1))
    assert completes and completes[0][1] is False
    assert not root.exists()


def test_viewer_file_stays_in_download_root(tmp_path):
    root = tmp_path / 'downloads'
    receiver = FileReceiver(base_dir=root)
    tid = new_transfer_id()
    receiver.handle_begin(encode_begin(tid, 'nested/result.txt', 3))
    receiver.handle_chunk(encode_chunk(tid, b'abc'))
    receiver.handle_end(encode_end(tid))
    assert (root / 'nested/result.txt').read_bytes() == b'abc'


def test_default_viewer_receiver_uses_download_root(tmp_path, monkeypatch):
    monkeypatch.setenv('JE_AUTOCONTROL_DOWNLOAD_DIR', str(tmp_path))
    viewer = RemoteDesktopViewer('localhost', 1, 'test-token')
    receiver = viewer._ensure_file_receiver()
    receiver.handle_begin(encode_begin(new_transfer_id(), '../escape', 0))
    assert not (tmp_path.parent / 'escape').exists()
    tid = new_transfer_id()
    receiver.handle_begin(encode_begin(tid, 'safe.txt', 0))
    receiver.handle_end(encode_end(tid))
    assert (tmp_path / 'safe.txt').exists()


def test_env_ref_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv('JE_AUTOCONTROL_MCP_ALLOWED_ENV', 'PUBLIC_SETTING')
    monkeypatch.setenv('PUBLIC_SETTING', 'ok')
    monkeypatch.setenv('PRIVATE_SETTING', 'hidden-token')
    server = MCPServer()
    assert _call(server, 'ac_resolve_ref', {'ref': 'env://PUBLIC_SETTING'})['isError'] is False
    result = _call(server, 'ac_resolve_refs', {'obj': {'deep': ['env://PRIVATE_SETTING']}})
    assert result['isError'] is True
    assert 'hidden-token' not in json.dumps(result)


def test_file_refs_use_the_same_roots(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'value.txt').write_text('public-value', encoding='utf-8')
    outside = tmp_path / 'outside.txt'
    outside.write_text('private-value', encoding='utf-8')
    monkeypatch.setenv('JE_AUTOCONTROL_MCP_ROOTS', str(root))
    server = MCPServer()
    assert _call(server, 'ac_resolve_ref', {'ref': 'file://value.txt'})['isError'] is False
    result = _call(server, 'ac_resolve_ref', {'ref': f'file://{outside}'})
    assert result['isError'] is True
    assert 'private-value' not in json.dumps(result)


def test_configured_and_client_roots_intersect_per_connection(tmp_path, monkeypatch):
    root = tmp_path / 'allowed'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    for directory in (root, outside):
        (directory / 'value.env').write_text('VALUE=ok', encoding='utf-8')
    monkeypatch.setenv('JE_AUTOCONTROL_MCP_ROOTS', str(root))
    server = MCPServer()
    with server.connection_scope(connection_id='a'):
        server._apply_roots([{'uri': outside.as_uri()}])
        assert _call(server, 'ac_load_dotenv', {'path': str(outside / 'value.env')})['isError']
        assert _call(server, 'ac_load_dotenv', {'path': str(root / 'value.env')})['isError']
    with server.connection_scope(connection_id='b'):
        server._apply_roots([{'uri': root.as_uri()}])
        assert not _call(server, 'ac_load_dotenv', {'path': str(root / 'value.env')})['isError']


def test_unconfigured_roots_preserve_file_access_but_deny_env_refs(tmp_path, monkeypatch):
    monkeypatch.delenv('JE_AUTOCONTROL_MCP_ROOTS', raising=False)
    monkeypatch.delenv('JE_AUTOCONTROL_MCP_ALLOWED_ENV', raising=False)
    path = tmp_path / 'settings.env'
    path.write_text('VALUE=ok', encoding='utf-8')
    monkeypatch.setenv('PRIVATE_SETTING', 'hidden-token')
    server = MCPServer()
    assert not _call(server, 'ac_load_dotenv', {'path': str(path)})['isError']
    assert _call(server, 'ac_resolve_ref', {'ref': 'env://PRIVATE_SETTING'})['isError']


@pytest.mark.parametrize('name, arguments', [
    ('ac_send_email', {'message': {'attachments': ['/outside/secret']}, 'smtp': {}}),
    ('ac_run_dag', {'definition': {'nodes': [{'id': 'a', 'action_file': '/outside/secret'}]}}),
    ('ac_act_in_view', {'target': '/outside/secret', 'kind': 'image'}),
    ('ac_open_path', {'target': '/outside/secret'}),
])
def test_nested_and_conditional_file_fields_are_checked_before_invocation(tmp_path, monkeypatch,
                                                                          name, arguments):
    from je_auto_control.utils.mcp_server._protocol import _InvalidToolArguments
    monkeypatch.setenv('JE_AUTOCONTROL_MCP_ROOTS', str(tmp_path))
    server = MCPServer()
    with pytest.raises(_InvalidToolArguments):
        server._prepare_tool_call({'name': name, 'arguments': arguments})


def test_conditional_text_and_url_arguments_are_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv('JE_AUTOCONTROL_MCP_ROOTS', str(tmp_path))
    server = MCPServer()
    for name, arguments in [('ac_act_in_view', {'target': 'a/b', 'kind': 'text'}),
                            ('ac_open_path', {'target': 'https://example.test'})]:
        _, _, prepared = server._prepare_tool_call({'name': name, 'arguments': arguments})
        assert prepared == arguments
