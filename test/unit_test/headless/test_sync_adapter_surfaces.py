"""Private adapter commands retain portable profile data across executor/MCP/Builder without runtime activation."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import authorize_command, capability_for_tool

NAMES = ('sync_adapter_snapshot', 'sync_adapter_apply', 'sync_adapter_resolve', 'sync_profile_materialize')


def profile(tmp_path, origin, source):
    return {'schema_version': 1, 'kind': 'scripts', 'state_path': str(tmp_path / (origin + '.sqlite3')),
            'identity': {'endpoint': 'https://controlled.invalid', 'user_id': 'alice', 'origin': origin},
            'source': source}


def tools():
    return {item.name: item for item in build_default_tool_registry() if item.name in {'ac_' + name for name in NAMES}}


def test_adapter_commands_capture_apply_materialize_and_builder_preserve_complete_json(tmp_path, monkeypatch):
    from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action
    root = tmp_path / 'scripts'
    root.mkdir()
    (root / 'login.json').write_text(json.dumps([['AC_log', {'message': 'inert'}]]))
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    sender = profile(tmp_path, 'desktop', {'path': str(root), 'paths': ['login.json']})
    receiver = profile(tmp_path, 'laptop', {'records': {}})
    snapshot = tools()['ac_sync_adapter_snapshot'].handler(sender)
    applied = tools()['ac_sync_adapter_apply'].handler(receiver, snapshot['entries'])
    assert applied['stored'] == ('login.json',) and not applied['conflicts']
    materialize = {'profiles': [receiver], 'target_root': str(tmp_path / 'cache')}
    result = tools()['ac_sync_profile_materialize'].handler(**materialize)
    from pathlib import Path
    assert (Path(result['directory']) / 'scripts' / 'login.json').is_file()
    actions = [['AC_sync_adapter_snapshot', {'profile': sender}],
               ['AC_sync_adapter_apply', {'profile': receiver, 'entries': snapshot['entries']}],
               ['AC_sync_profile_materialize', materialize]]
    for action in actions:
        assert step_to_action(action_to_step(action)) == action
        ac.executor.execute_action([action], raise_on_error=True)


def test_adapter_surfaces_are_private_and_prestart_refusal_creates_no_database(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    with authorization_scope(AuthorizationContext('viewer', Role.VIEWER)):
        for name in NAMES:
            with pytest.raises(AuthorizationError):
                authorize_command('AC_' + name)
            assert capability_for_tool('ac_' + name, True) == 'drive_input'
    receiver = profile(tmp_path, 'laptop', {'records': {}})
    ctx = ToolCallContext('cancelled')
    ctx.cancelled_event.set()
    with pytest.raises(OperationCancelledError):
        tools()['ac_sync_adapter_snapshot'].handler(receiver, ctx=ctx)
    ctx = ToolCallContext('confined', path_policy=PathPolicy([tmp_path / 'other']))
    with pytest.raises(PathNotAllowedError):
        tools()['ac_sync_adapter_snapshot'].handler(receiver, ctx=ctx)
    assert not (tmp_path / 'laptop.sqlite3').exists()


def test_adapter_resolution_command_binds_the_exact_reviewed_versions(tmp_path, monkeypatch):
    from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    receiver = profile(tmp_path, 'laptop', {'records': {}})
    entries = [ac.SyncEntry('scripts', 'login.json', {'actions': [['AC_log', {'message': value}]]},
                            {origin: 1}, 'edit-' + origin, origin) for origin, value in [('one', 'a'), ('two', 'b')]]
    report = tools()['ac_sync_adapter_apply'].handler(receiver, {item.change_id: item.to_dict() for item in entries})
    assert report['conflicts'] == ('login.json',)
    arguments = {'profile': receiver, 'entry_id': 'login.json', 'value': entries[0].value,
                 'observed': [item.change_id for item in entries]}
    action = ['AC_sync_adapter_resolve', arguments]
    assert step_to_action(action_to_step(action)) == action
    assert tools()['ac_sync_adapter_resolve'].handler(**arguments)['version'] == {'one': 1, 'two': 1, 'laptop': 1}
    with pytest.raises(ac.ConfigSyncError):
        tools()['ac_sync_adapter_resolve'].handler(**arguments)


@pytest.mark.parametrize('change', ['cancel', 'roots'])
def test_materialization_keeps_the_source_profiles_authority_live_until_publication(tmp_path, monkeypatch, change):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    receiver = profile(tmp_path, 'laptop', {'records': {}})
    entry = ac.SyncEntry('scripts', 'login.json', {'actions': []}, {'one': 1}, 'first', 'one')
    tools()['ac_sync_adapter_apply'].handler(receiver, {entry.change_id: entry.to_dict()})
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([tmp_path])
    ctx = ToolCallContext('profile-live-authority', path_policy=policy)
    original = ac.DirectoryAssetTransport.open
    def revoke(instance, asset):
        stream = original(instance, asset)
        if change == 'cancel':
            ctx.cancelled_event.set()
        else:
            policy.set_client_roots([tmp_path / 'cache'])
        return stream
    monkeypatch.setattr(ac.DirectoryAssetTransport, 'open', revoke)
    expected = OperationCancelledError if change == 'cancel' else PathNotAllowedError
    with pytest.raises(expected):
        tools()['ac_sync_profile_materialize'].handler([receiver], str(tmp_path / 'cache'), ctx=ctx)
    assert not list((tmp_path / 'cache').glob('generation-*'))
    assert not list((tmp_path / 'cache').glob('.incoming-*'))
