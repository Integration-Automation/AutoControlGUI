"""Peer-control API, executor, MCP and Builder share explicit retirement consent and private local review."""
import pytest

import je_auto_control as ac
from headless.test_config_sync_peer_control import peer
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import authorize_command, capability_for_tool


def tool():
    return next(item for item in build_default_tool_registry() if item.name == 'ac_sync_peer_control')


def test_peer_control_commands_and_builder_preserve_explicit_json_and_cached_review(tmp_path, monkeypatch):
    from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action
    _client, queue, server, calls, _perform = peer(tmp_path, monkeypatch)
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    arguments = {'path': str(tmp_path / 'outbox.sqlite3'), 'endpoint': 'https://controlled.invalid',
                 'user_id': 'alice', 'operation': 'register', 'options': {'operation_id': 'join-desktop'}}
    action = ['AC_sync_peer_control', arguments]
    assert step_to_action(action_to_step(action)) == action
    ac.executor.execute_action([action], raise_on_error=True)
    assert server.get('alice').peers.require_active('desktop', epoch=0)
    before = len(calls)
    assert tool().handler(**arguments)['report']['revision'] == 1
    assert len(calls) == before
    arguments['operation'] = 'status'
    arguments['options'] = {'secret_env': 'UNSET_CONTROL_REVIEW_SECRET'}
    monkeypatch.delenv('UNSET_CONTROL_REVIEW_SECRET', raising=False)
    result = tool().handler(**arguments)
    assert result['control']['state'] == 'delivered'
    assert result['snapshot'] == queue.snapshot(endpoint=arguments['endpoint'], user_id='alice').to_dict()
    assert len(calls) == before


def test_peer_control_is_private_and_cancellation_or_path_refusal_precedes_storage(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    with authorization_scope(AuthorizationContext('viewer', Role.VIEWER)):
        with pytest.raises(AuthorizationError):
            authorize_command('AC_sync_peer_control')
        assert capability_for_tool('ac_sync_peer_control', True) == 'drive_input'
    arguments = {'path': str(tmp_path / 'unused.sqlite3'), 'endpoint': 'https://controlled.invalid',
                 'user_id': 'alice', 'operation': 'register'}
    ctx = ToolCallContext('cancelled')
    ctx.cancelled_event.set()
    with pytest.raises(OperationCancelledError):
        tool().handler(**arguments, ctx=ctx)
    assert not (tmp_path / 'unused.sqlite3').exists()
    ctx = ToolCallContext('confined', path_policy=PathPolicy([tmp_path / 'elsewhere']))
    with pytest.raises(PathNotAllowedError):
        tool().handler(**arguments, ctx=ctx)
    assert not (tmp_path / 'unused.sqlite3').exists()


def test_peer_control_mid_fetch_cancellation_preserves_protocol_signal_and_local_intent(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    _client, queue, _server, calls, perform = peer(tmp_path, monkeypatch)
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    ctx = ToolCallContext('peer-mid-fetch')
    def cancel(call):
        response = perform(call)
        ctx.cancelled_event.set()
        return response
    monkeypatch.setattr(http_client, 'perform_call', cancel)
    with pytest.raises(OperationCancelledError):
        tool().handler(path=str(tmp_path / 'outbox.sqlite3'), endpoint='https://controlled.invalid',
                       user_id='alice', operation='register', ctx=ctx)
    assert [call['method'] for call in calls] == ['GET']
    status = queue.control_status(endpoint='https://controlled.invalid', user_id='alice')
    assert status['pending'] == 1 and status['state'] == 'pending' and status['error'] == ''
