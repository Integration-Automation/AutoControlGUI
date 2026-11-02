"""Existing Python, command, CLI and HTTP skill publication share explicit completion adoption."""
import json

import pytest

from headless.test_agent_skill_completion import acceptance, trial as _trial
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.rest_api.rest_server import RestApiServer

trial = _trial


@pytest.mark.parametrize('surface', ['python', 'executor', 'cli', 'rest', 'mcp'])
def test_shared_surfaces_publish_the_original_trial_with_explicit_completion(trial, monkeypatch, tmp_path, surface):
    import je_auto_control as ac
    from je_auto_control.cli import build_parser
    from je_auto_control.utils.agent_runtime.cli import run
    from je_auto_control.utils.tool_use_schema import run_tool_call
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
    server = RestApiServer(port=0, token='owned-skill-completion', agent_runtime=trial.runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = tmp_path / 'connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': server.token}), encoding='utf-8')
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path', lambda: connection)
        request = acceptance(trial)
        tools = {tool.name: tool for tool in build_default_tool_registry()}
        if surface == 'python':
            value = ac.manage_agent_skill('accept', request)
        elif surface == 'executor':
            value = run_tool_call('AC_agent_skill', {'operation': 'accept', 'request': request})
        elif surface == 'cli':
            path = tmp_path / 'accept.json'
            path.write_text(json.dumps(request), encoding='utf-8')
            value = run(build_parser().parse_args(['agent-task', 'skill', 'accept', str(path)]))
        elif surface == 'mcp':
            with authorization_scope(AuthorizationContext('owned-reviewer', 'admin')):
                value = tools['ac_agent_skill'].invoke({'operation': 'accept', 'request': request})
        else:
            value = AgentRuntimeClient(connection).call('skill', {'operation': 'accept', 'request': request})
        assert value['publication']['task_id'] == trial.task_id and value['version'] == 1
        assert value['publication']['completion_review']['task_id'] == trial.child_id
        assert trial.runtime.get(trial.task_id).state == 'paused'
        assert 'accept' in tools['ac_agent_skill'].input_schema['properties']['operation']['enum']
        assert 'AC_agent_skill' in COMMAND_SPECS
    finally:
        server.stop()
