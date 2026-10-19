"""Private causal HTTP commands share credential references, path limits and Builder data round trips."""
import pytest

import je_auto_control as ac
from headless.test_config_sync_causal_client import connected
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import authorize_command, capability_for_tool


NAMES = ['config_causal_fetch', 'config_causal_commit', 'sync_outbox_flush']


def tools():
    return {item.name: item for item in build_default_tool_registry() if item.name in {'ac_' + name for name in NAMES}}


def test_causal_http_commands_and_builder_use_explicit_json_and_live_environment_credentials(tmp_path, monkeypatch):
    from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action
    _client, queue, operation, server, calls, _perform = connected(tmp_path, monkeypatch)
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    monkeypatch.setenv('AC_TEST_CAUSAL_SHARED_SECRET', 'synthetic-only')
    options = {'secret_env': 'AC_TEST_CAUSAL_SHARED_SECRET'}
    common = {'endpoint': operation.endpoint, 'user_id': 'alice', 'options': options}
    fetch = tools()['ac_config_causal_fetch'].handler(**common)
    state = ac.CausalBucket.from_dict(fetch['bucket'])
    commit = dict(common, bucket=state.with_entries(operation.entries).to_dict(),
                  actor=ac.SyncActor('desktop', 0).to_dict(), operation_id='explicit-commit')
    result = tools()['ac_config_causal_commit'].handler(**commit)
    assert result['revision'] == 2 and result['bucket']['revision'] == 2
    flush = dict(common, path=str(tmp_path / 'outbox.sqlite3'))
    result = tools()['ac_sync_outbox_flush'].handler(**flush)
    assert result['report']['delivered'] == 1 and result['snapshot'] == server.get('alice').to_dict()
    for command, args in [('AC_config_causal_fetch', common), ('AC_config_causal_commit', commit),
                          ('AC_sync_outbox_flush', flush)]:
        action = [command, args]
        assert step_to_action(action_to_step(action)) == action
    assert queue.status(endpoint=operation.endpoint, user_id='alice')['pending'] == 0
    assert all(call['headers']['X-Signaling-Secret'] == 'synthetic-only' for call in calls)
    assert b'synthetic-only' not in (tmp_path / 'outbox.sqlite3').read_bytes()


def test_causal_http_tools_require_drive_even_when_reading_and_cancel_before_storage(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    with authorization_scope(AuthorizationContext('viewer', Role.VIEWER)):
        for name in NAMES:
            with pytest.raises(AuthorizationError):
                authorize_command('AC_' + name)
            assert capability_for_tool('ac_' + name, True) == 'drive_input'
    ctx = ToolCallContext('cancelled')
    ctx.cancelled_event.set()
    args = {'path': str(tmp_path / 'outbox.sqlite3'), 'endpoint': 'https://controlled.invalid', 'user_id': 'alice'}
    with pytest.raises(OperationCancelledError):
        tools()['ac_sync_outbox_flush'].handler(**args, ctx=ctx)
    assert not (tmp_path / 'outbox.sqlite3').exists()
    ctx = ToolCallContext('confined', path_policy=PathPolicy([tmp_path / 'elsewhere']))
    with pytest.raises(PathNotAllowedError):
        tools()['ac_sync_outbox_flush'].handler(**args, ctx=ctx)
    assert not (tmp_path / 'outbox.sqlite3').exists()


def test_mid_request_mcp_cancellation_preserves_its_protocol_signal_and_durable_edit(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    _client, queue, operation, _server, calls, perform = connected(tmp_path, monkeypatch)
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    monkeypatch.setenv('AC_TEST_CAUSAL_SHARED_SECRET', 'synthetic-only')
    ctx = ToolCallContext('mid-request')
    def cancelled_after_fetch(call):
        response = perform(call)
        if call['method'] == 'GET':
            ctx.cancelled_event.set()
        return response
    monkeypatch.setattr(http_client, 'perform_call', cancelled_after_fetch)
    with pytest.raises(OperationCancelledError):
        tools()['ac_sync_outbox_flush'].handler(path=str(tmp_path / 'outbox.sqlite3'), endpoint=operation.endpoint,
            user_id='alice', options={'secret_env': 'AC_TEST_CAUSAL_SHARED_SECRET'}, ctx=ctx)
    assert [call['method'] for call in calls] == ['GET']
    state = queue.status(endpoint=operation.endpoint, user_id='alice')
    assert state['pending'] == 1 and state['offline'] == 0
