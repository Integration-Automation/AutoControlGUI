"""Private CAS commands share durable revisions across executor, MCP and Builder."""
import pytest

import je_auto_control as ac
from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import authorize_command, capability_for_tool


def tools():
    return {item.name:item for item in build_default_tool_registry() if item.name.startswith('ac_config_store_')}


def arguments(tmp_path):
    return {'path':str(tmp_path/'config.sqlite3'),'user_id':'alice',
            'bucket':ac.ConfigBucket('alice').to_dict(),'base_revision':0,'operation_id':'first'}


def test_executor_mcp_and_builder_share_store_and_journal_evidence(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS',str(tmp_path))
    args=arguments(tmp_path)
    source=ac.ActionJournal(tmp_path/'journal.jsonl')
    with ac.journal_scope(source,run_id='config-commit'):
        ac.executor.execute_action([['AC_config_store_commit',args]],raise_on_error=True)
    reply=tools()['ac_config_store_commit'].handler(**args)
    assert reply=={'version':2,'revision':1,'cas':True}
    read=tools()['ac_config_store_get'].handler(path=args['path'],user_id='alice')
    assert read['bucket']['revision']==1 and read['cas'] is True
    assert {'AC_config_store_commit','AC_config_store_get'}<=COMMAND_SPECS.keys()
    candidate=ac.generate_candidate_from_log(source.path,run_id='config-commit')
    assert candidate.actions==[['AC_config_store_commit',args]]
    assert ac.ConfigStore(args['path']).get('alice').revision==1


def test_private_store_reads_and_writes_require_drive():
    with authorization_scope(AuthorizationContext('viewer',Role.VIEWER)):
        for name in ['AC_config_store_get','AC_config_store_commit']:
            with pytest.raises(AuthorizationError):
                authorize_command(name)
    assert all(capability_for_tool(name,True)=='drive_input' for name in tools())


def test_cancelled_or_confined_mcp_does_not_open_a_database(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS',str(tmp_path))
    args=arguments(tmp_path)
    ctx=ToolCallContext('cancelled')
    ctx.cancelled_event.set()
    with pytest.raises(OperationCancelledError):
        tools()['ac_config_store_commit'].handler(**args,ctx=ctx)
    ctx=ToolCallContext('confined',path_policy=PathPolicy([tmp_path/'elsewhere']))
    with pytest.raises(PathNotAllowedError):
        tools()['ac_config_store_commit'].handler(**args,ctx=ctx)
    assert not (tmp_path/'config.sqlite3').exists()


def test_signaling_cli_exposes_persistence_and_compatibility_flags(tmp_path):
    pytest.importorskip('fastapi')
    from je_auto_control.utils.remote_desktop.signaling_server import _build_arg_parser
    args=_build_arg_parser().parse_args(['--config-store',str(tmp_path/'config.sqlite3'),
                                       '--allow-legacy-config-writes'])
    assert args.allow_legacy_config_writes is True
    assert args.config_store.endswith('config.sqlite3')
