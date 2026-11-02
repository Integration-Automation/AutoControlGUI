"""Public transfer surfaces use the same owned service and never mint consent merely by listing."""
import json

import pytest

from headless.test_agent_transfer_source import completed_source
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.rest_api.rest_server import RestApiServer


@pytest.fixture
def transfer_service(tmp_path, monkeypatch):
    from types import SimpleNamespace
    with completed_source(tmp_path) as (runtime, source, output, body, _users):
        server = RestApiServer(port=0, token='owned-public-transfer', agent_runtime=runtime,
            enable_audit=False, use_environment_users=False)
        server.start()
        try:
            connection = tmp_path / 'connection.json'
            connection.write_text(json.dumps({'url': server.base_url, 'token': server.token}), encoding='utf-8')
            monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path',
                                lambda: connection)
            yield SimpleNamespace(runtime=runtime, source=source, output=output, body=body, connection=connection)
        finally:
            server.stop()


@pytest.mark.parametrize('surface', ['python', 'core', 'executor', 'mcp', 'cli', 'rest'])
def test_shared_transfer_surfaces_list_the_actual_source_without_creating_a_grant(transfer_service, tmp_path, surface):
    import je_auto_control as ac
    from je_auto_control.api import core
    from je_auto_control.cli import build_parser
    from je_auto_control.utils.agent_runtime.cli import run
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
    from je_auto_control.utils.tool_use_schema import run_tool_call
    value = transfer_service
    request = {'source_task': value.source}
    if surface == 'python':
        result = ac.manage_agent_transfer('list_exports', request)
    elif surface == 'core':
        result = core.manage_agent_transfer('list_exports', request)
    elif surface == 'executor':
        result = run_tool_call('AC_agent_transfer', {'operation': 'list_exports', 'request': request})
    elif surface == 'mcp':
        tools = {tool.name: tool for tool in build_default_tool_registry()}
        with authorization_scope(AuthorizationContext('owned-transfer-reviewer', 'admin')):
            result = tools['ac_agent_transfer'].invoke({'operation': 'list_exports', 'request': request})
    elif surface == 'cli':
        path = tmp_path / 'transfer-request.json'
        path.write_text(json.dumps(request), encoding='utf-8')
        result = run(build_parser().parse_args(['agent-task', 'transfer', '--operation', 'list_exports',
                                               '--request', str(path)]))
    else:
        result = AgentRuntimeClient(value.connection).call('transfer', {
            'operation': 'list_exports', 'request': request})
    assert result == {'exports': []}
    assert value.runtime.get(value.source).state == 'succeeded' and value.runtime.store.actions(value.source) == []
    assert value.output.read_bytes() == value.body
    with value.runtime.store.connection() as database:
        assert database.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0] == 0


def test_public_api_names_and_builder_fields_share_the_same_management_contract():
    import je_auto_control as ac
    from je_auto_control import api
    from je_auto_control.api import core
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    from je_auto_control.utils import agent_runtime
    from je_auto_control.utils.agent_runtime.commands import CATALOG
    from je_auto_control.utils.agent_runtime.transfer_operations import OPERATIONS

    assert ac.manage_agent_transfer is api.manage_agent_transfer is core.manage_agent_transfer
    assert ac.manage_agent_transfer is agent_runtime.manage_agent_transfer
    for module in (ac, api, core, agent_runtime):
        assert 'manage_agent_transfer' in module.__all__
    function, fields, required, readonly, management = CATALOG['AC_agent_transfer']
    assert function is ac.manage_agent_transfer and required == ('operation',)
    assert readonly is False and management is False
    assert fields['operation']['enum'] == list(OPERATIONS)
    assert not {'export', 'chunk', 'evidence'} & set(fields['operation']['enum'])
    specification = COMMAND_SPECS['AC_agent_transfer']
    assert [field.name for field in specification.fields] == ['operation', 'request']
    assert [field.optional for field in specification.fields] == [False, True]


def test_transfer_management_is_not_an_executable_managed_task_tool(tmp_path):
    from je_auto_control.utils.agent_runtime import AgentTaskError

    with completed_source(tmp_path) as (runtime, _source, output, _body, _users):
        with pytest.raises(AgentTaskError, match='not allowed'):
            runtime.submit({'goal': 'Reject recursive grant management', 'target': 'local-files',
                'allowed_tools': ['AC_agent_transfer'], 'roots': [str(tmp_path)],
                'success_criteria': [{'kind': 'file_exists', 'path': str(output)}]})
        assert len(runtime.list()) == 1


def test_public_creation_requires_its_review_and_keeps_peer_reads_on_the_separate_protocol(transfer_service):
    from hashlib import sha256
    import je_auto_control as ac
    from je_auto_control.utils.agent_runtime import AgentTaskError
    value = transfer_service
    reviewed = ac.manage_agent_transfer('review_export', {'source_task': value.source,
        'selection': [{'criterion': 0, 'names': []}], 'recipient_policy': 'caller',
        'idempotency_key': 'public-consent-flow'})
    assert reviewed['approval_required'] is True
    with value.runtime.store.connection() as database:
        assert database.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0] == 0
    request = {'review': reviewed['review'], 'note': 'Explicitly approve this selected source outcome',
               'idempotency_key': 'public-consent-flow'}
    first = ac.manage_agent_transfer('create_export', request)
    second = ac.manage_agent_transfer('create_export', request)
    assert first == second and first['export']['state'] == 'active'
    manifest = first['export']['manifest']
    assert manifest['files'][0]['sha256'] == sha256(value.body).hexdigest()
    identifier = first['export']['export_id']
    with pytest.raises(AgentTaskError):
        ac.manage_agent_transfer('export', {'export_id': identifier})
    assert value.runtime.transfers.peer('export', {'export_id': identifier}) == manifest
    with value.runtime.store.connection() as database:
        assert database.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0] == 1
    assert value.output.read_bytes() == value.body and value.runtime.store.actions(value.source) == []
