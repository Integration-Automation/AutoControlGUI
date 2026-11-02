"""Shared skill surfaces review and explicitly adopt the exact original recovered validation trial."""
import json

import pytest

from headless.test_agent_skill_execution import execution as _execution, review_request
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.rest_api.rest_server import RestApiServer

execution = _execution


def invoke(surface, connection, temporary, operation, request):
    import je_auto_control as ac
    from je_auto_control.cli import build_parser
    from je_auto_control.utils.agent_runtime.cli import run
    from je_auto_control.utils.tool_use_schema import run_tool_call
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
    if surface == 'python':
        return ac.manage_agent_skill(operation, request)
    if surface == 'executor':
        return run_tool_call('AC_agent_skill', {'operation': operation, 'request': request})
    if surface == 'cli':
        path = temporary / 'request.json'
        path.write_text(json.dumps(request), encoding='utf-8')
        return run(build_parser().parse_args(['agent-task', 'skill', operation, str(path)]))
    if surface == 'mcp':
        tool = next(item for item in build_default_tool_registry() if item.name == 'ac_agent_skill')
        assert 'review_execution' in tool.input_schema['properties']['operation']['enum']
        with authorization_scope(AuthorizationContext('owned-execution-reviewer', 'admin')):
            return tool.invoke({'operation': operation, 'request': request})
    return AgentRuntimeClient(connection).call('skill', {'operation': operation, 'request': request})


@pytest.mark.parametrize('surface', ['python', 'executor', 'cli', 'rest', 'mcp'])
def test_shared_surfaces_review_then_accept_complete_recovered_trial(execution, monkeypatch, tmp_path, surface):
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    assert 'AC_agent_skill' in COMMAND_SPECS
    server = RestApiServer(port=0, token='owned-execution-chain', agent_runtime=execution.runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = tmp_path / 'connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': server.token}), encoding='utf-8')
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path', lambda: connection)
        request = review_request(execution)
        review = invoke(surface, connection, tmp_path, 'review_execution', request)
        assert review['approval_required'] is True and review['publication_inherited'] is False
        accepted = invoke(surface, connection, tmp_path, 'accept', {**request,
            'execution_review': review['execution_review'], 'expected_version': 0,
            'note': 'Reviewed exact full original execution chain'})
        assert accepted['publication']['task_id'] == execution.task_id and accepted['version'] == 1
        assert accepted['publication']['execution_review']['task_id'] == execution.child_id
        assert execution.runtime.get(execution.task_id).state == 'paused'
    finally:
        server.stop()
