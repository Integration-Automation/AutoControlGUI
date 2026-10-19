"""Explicit asset commands retain manifest JSON and enforce private, confined, cancellable transfers."""
import pytest

import je_auto_control as ac
from headless.test_sync_assets import asset_bundle
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import authorize_command, capability_for_tool


def test_asset_commands_mcp_and_builder_preserve_explicit_manifest_and_verified_files(tmp_path, monkeypatch):
    from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action
    source, manifest, transport = asset_bundle(tmp_path)
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    capture = {'source_root': str(source), 'paths': [item.path for item in manifest.files]}
    assert tools['ac_sync_asset_manifest'].handler(**capture)['manifest'] == manifest.to_dict()
    arguments = {'manifest': manifest.to_dict(), 'source_root': str(source), 'target_root': str(transport.target_root)}
    result = tools['ac_sync_assets'].handler(**arguments)
    assert result['manifest_digest'] == manifest.digest and result['file_count'] == 2
    for command, args in [('AC_sync_asset_manifest', capture), ('AC_sync_assets', arguments)]:
        action = [command, args]
        assert step_to_action(action_to_step(action)) == action
        ac.executor.execute_action([action], raise_on_error=True)


def test_asset_surfaces_require_drive_and_reject_paths_or_cancel_before_target_creation(tmp_path, monkeypatch):
    source, manifest, transport = asset_bundle(tmp_path)
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    with authorization_scope(AuthorizationContext('viewer', Role.VIEWER)):
        for suffix in ('sync_asset_manifest', 'sync_assets'):
            with pytest.raises(AuthorizationError):
                authorize_command('AC_' + suffix)
            assert capability_for_tool('ac_' + suffix, True) == 'drive_input'
    arguments = {'manifest': manifest.to_dict(), 'source_root': str(source), 'target_root': str(transport.target_root)}
    ctx = ToolCallContext('asset-cancel')
    ctx.cancelled_event.set()
    with pytest.raises(OperationCancelledError):
        tools['ac_sync_assets'].handler(**arguments, ctx=ctx)
    ctx = ToolCallContext('asset-confined', path_policy=PathPolicy([source]))
    with pytest.raises(PathNotAllowedError):
        tools['ac_sync_assets'].handler(**arguments, ctx=ctx)
    assert not transport.target_root.exists()


@pytest.mark.parametrize('change', ['cancel', 'roots'])
def test_asset_mcp_live_authority_change_stops_before_publication(tmp_path, monkeypatch, change):
    source, manifest, transport = asset_bundle(tmp_path)
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([tmp_path])
    ctx = ToolCallContext('asset-live-authority', path_policy=policy)
    original = ac.DirectoryAssetTransport.open
    def revoke(instance, asset):
        stream = original(instance, asset)
        if change == 'cancel':
            ctx.cancelled_event.set()
        else:
            policy.set_client_roots([])
        return stream
    monkeypatch.setattr(ac.DirectoryAssetTransport, 'open', revoke)
    tool = next(item for item in build_default_tool_registry() if item.name == 'ac_sync_assets')
    expected = OperationCancelledError if change == 'cancel' else PathNotAllowedError
    with pytest.raises(expected):
        tool.handler(manifest.to_dict(), str(source), str(transport.target_root), ctx=ctx)
    assert not list(transport.target_root.glob('generation-*'))
    assert not list(transport.target_root.glob('.incoming-*'))
