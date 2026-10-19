"""Workspace coordination shares private JSON routing and live authority across AC, MCP and Builder."""
from pathlib import Path

import pytest

import je_auto_control as ac
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import authorize_command, capability_for_tool


def configuration(tmp_path, entry_id='login.json'):
    return {'schema_version': 1, 'endpoint': 'https://controlled.invalid', 'user_id': 'alice',
            'outbox_path': str(tmp_path / 'outbox.sqlite3'), 'profiles': [
                {'kind': 'scripts', 'state_path': str(tmp_path / 'adapters.sqlite3'),
                 'source': {'records': {entry_id: {'actions': []}}}}]}


def tool():
    return next(item for item in build_default_tool_registry() if item.name == 'ac_sync_workspace')


@pytest.mark.parametrize('entry_id', ['login.json', 'flows/login.json', 'x' * 64 + '/' + 'y' * 64 + '.json'])
def test_workspace_command_mcp_builder_capture_review_and_materialize(tmp_path, monkeypatch, entry_id):
    from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    config = configuration(tmp_path, entry_id)
    arguments = {'configuration': config, 'operation': 'capture'}
    action = ['AC_sync_workspace', arguments]
    assert step_to_action(action_to_step(action)) == action
    ac.executor.execute_action([action], raise_on_error=True)
    assert tool().handler(config)['outbox']['pending'] == 1
    assert tool().handler(config, 'capture') == {'captured': 0}
    heads = tool().handler(config, 'review', {'kind': 'scripts'})['entries']
    assert len(heads) == 1
    options = {'kind': 'scripts', 'entry_id': entry_id, 'value': {'actions': [['AC_log', {'message': 'chosen'}]]},
               'observed': list(heads)}
    chosen = tool().handler(config, 'resolve', options)
    assert chosen['value'] == options['value']
    result = tool().handler(config, 'materialize', {'target_root': str(tmp_path / 'cache')})
    assert (Path(result['directory']) / 'scripts' / entry_id).is_file()
    for operation, options in [('status', {}), ('review', {'kind': 'scripts'}), ('resolve', options),
                               ('sync', {'timeout_s': 1}), ('full_resync', {'discard_pending': True}),
                               ('materialize', {'target_root': str(tmp_path / 'cache')})]:
        action = ['AC_sync_workspace', {'configuration': config, 'operation': operation, 'options': options}]
        assert step_to_action(action_to_step(action)) == action


def test_workspace_status_is_drive_only_and_prestart_refusal_has_no_database(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    config = configuration(tmp_path)
    with authorization_scope(AuthorizationContext('viewer', Role.VIEWER)):
        with pytest.raises(AuthorizationError):
            authorize_command('AC_sync_workspace')
        assert capability_for_tool('ac_sync_workspace', True) == 'drive_input'
    ctx = ToolCallContext('cancelled')
    ctx.cancelled_event.set()
    with pytest.raises(OperationCancelledError):
        tool().handler(config, ctx=ctx)
    ctx = ToolCallContext('confined', path_policy=PathPolicy([tmp_path / 'other']))
    with pytest.raises(PathNotAllowedError):
        tool().handler(config, ctx=ctx)
    assert not list(tmp_path.glob('*.sqlite3'))


@pytest.mark.parametrize('operation,options', [('unknown', {}), ('capture', {'secret_env': 'UNUSED'}),
    ('review', {}), ('review', {'kind': 'unknown'}), ('resolve', {'kind': 'scripts'}),
    ('materialize', {'target_root': 42}), ('sync', {'secret': 'never-read'}),
    ('full_resync', {'discard_pending': 'yes'}), ('retire', {})])
def test_workspace_routing_rejects_invalid_arguments_before_io(tmp_path, monkeypatch, operation, options):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    with pytest.raises(ac.ConfigSyncError):
        tool().handler(configuration(tmp_path), operation, options)
    assert not list(tmp_path.glob('*.sqlite3'))
