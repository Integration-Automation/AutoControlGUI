"""Causal model and durable queue adapters use bounded JSON and never contact a server."""
import pytest

from headless.test_config_sync_convergence import entry
from headless.test_config_sync_outbox import operation
from je_auto_control import executor
from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import authorize_command, capability_for_tool


def tools():
    return {item.name:item for item in build_default_tool_registry() if item.name.startswith('ac_sync_')}


def test_merge_command_preserves_both_json_alternatives_without_dispatch(monkeypatch):
    def forbidden(*_args,**_kwargs):
        pytest.fail('data-only merge must never dispatch')
    monkeypatch.setattr(executor,'_execute_event',forbidden)
    left,right=entry('desktop','dark').to_dict(),entry('laptop','light').to_dict()
    args={'left':left,'right':right}
    command=executor.event_dict['AC_sync_entry_merge'](**args)
    assert command==tools()['ac_sync_entry_merge'].handler(**args)
    assert command['conflict']['local']==left and command['conflict']['remote']==right
    assert 'AC_sync_entry_merge' in COMMAND_SPECS


def test_enqueue_and_status_share_a_local_store_and_explicit_builder_fields(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS',str(tmp_path))
    def forbidden(*_args,**_kwargs):
        pytest.fail('queue inspection must never perform HTTP')
    monkeypatch.setattr('je_auto_control.utils.config_sync.client.ConfigSyncClient._request',forbidden)
    item=operation()
    args={'path':str(tmp_path/'queue.sqlite3'),'operation':item.to_dict()}
    accepted=executor.event_dict['AC_sync_outbox_enqueue'](**args)
    assert accepted['accepted'] is True and accepted['state']['pending']==1
    result=tools()['ac_sync_outbox_status'].handler(path=args['path'],endpoint=item.endpoint,user_id='alice',
                                                  include_pending=True,limit=1)
    assert result['operations']==[item.to_dict()] and result['truncated'] is False
    assert {'AC_sync_outbox_enqueue','AC_sync_outbox_status'}<=COMMAND_SPECS.keys()


def test_private_queue_access_is_drive_but_supplied_data_transforms_are_observable():
    with authorization_scope(AuthorizationContext('viewer',Role.VIEWER)):
        for name in ['AC_sync_outbox_enqueue','AC_sync_outbox_status']:
            with pytest.raises(AuthorizationError):
                authorize_command(name)
        for name in ['AC_sync_entry_merge','AC_sync_peer_state']:
            authorize_command(name)
    assert capability_for_tool('ac_sync_outbox_status',True)=='drive_input'
    assert capability_for_tool('ac_sync_entry_merge',True)=='read_screen'


def test_cancelled_or_confined_queue_tools_do_not_create_a_database(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS',str(tmp_path))
    args={'path':str(tmp_path/'queue.sqlite3'),'operation':operation().to_dict()}
    ctx=ToolCallContext('cancelled')
    ctx.cancelled_event.set()
    with pytest.raises(OperationCancelledError):
        tools()['ac_sync_outbox_enqueue'].handler(**args,ctx=ctx)
    ctx=ToolCallContext('confined',path_policy=PathPolicy([tmp_path/'elsewhere']))
    with pytest.raises(PathNotAllowedError):
        tools()['ac_sync_outbox_enqueue'].handler(**args,ctx=ctx)
    assert not (tmp_path/'queue.sqlite3').exists()


def test_peer_state_command_only_transforms_the_supplied_ledger():
    from je_auto_control.utils.config_sync.peers import SyncPeers
    peer=executor.event_dict['AC_sync_peer_state']
    state=peer(state=SyncPeers().to_dict(),operation='register',peer_id='desktop',revision=0)['state']
    result=peer(state=state,operation='acknowledge',peer_id='desktop',revision=3,epoch=0)
    assert peer(state=result['state'],operation='can_collect',revision=3)['result'] is True
    assert state['peers'][0]['acknowledged_revision']==0
    assert 'AC_sync_peer_state' in COMMAND_SPECS
