"""All shared surfaces keep actual named principals for explicit non-DAG evidence adoption."""
import json

import pytest

from headless.test_agent_task_handoff import recording as _recording, trial as _trial
from headless.test_agent_skill_completion import acceptance
from headless.test_agent_skill_recording_completion import request_for
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.rest_api.rest_server import RestApiServer
from je_auto_control.utils.rbac.authorization import authorization_scope

recording = _recording
trial = _trial
SURFACES = ['python', 'executor', 'cli', 'rest', 'mcp']


def invoke(surface, group, operation, request, connection, temporary):
    import je_auto_control as ac
    from je_auto_control.cli import build_parser
    from je_auto_control.utils.agent_runtime.cli import run
    from je_auto_control.utils.tool_use_schema import run_tool_call
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    if surface == 'python':
        function = ac.manage_agent_recovery if group == 'recovery' else ac.manage_agent_skill
        return function(operation, request)
    if surface == 'executor':
        command = 'AC_agent_task_recovery' if group == 'recovery' else 'AC_agent_skill'
        return run_tool_call(command, {'operation': operation, 'request': request})
    if surface == 'cli':
        path = temporary / 'task-handoff-request.json'
        path.write_text(json.dumps(request), encoding='utf-8')
        return run(build_parser().parse_args(['agent-task', group, operation, str(path)]))
    if surface == 'mcp':
        name = 'ac_agent_task_recovery' if group == 'recovery' else 'ac_agent_skill'
        tool = next(item for item in build_default_tool_registry() if item.name == name)
        return tool.invoke({'operation': operation, 'request': request})
    return AgentRuntimeClient(connection).call(group, {'operation': operation, 'request': request})


def exercise(value, surface, operation, adoption, monkeypatch, temporary):
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    assert {'AC_agent_task_recovery', 'AC_agent_skill'} <= COMMAND_SPECS.keys()
    runtime = value.runtime
    server = RestApiServer(port=0, token='owned-task-handoff-surfaces', agent_runtime=runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = temporary / 'connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': server.token}), encoding='utf-8')
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path', lambda: connection)
        with pytest.raises(AgentTaskError):
            AgentRuntimeClient(connection).call('get', {'task_id': value.child_id})
        request = {'source_task': value.task_id, 'task_id': value.child_id}
        with authorization_scope(value.reviewer):
            preview = invoke(surface, 'recovery', 'review_handoff', request, connection, temporary)
            grant = invoke(surface, 'recovery', 'create_handoff', {**request, 'review': preview['handoff_review'],
                'note': 'Explicit actual named-caller non-DAG evidence handoff'}, connection, temporary)['handoff']
        with runtime.store.connection() as reading:
            proof = json.loads(reading.execute('SELECT details FROM agent_task_handoffs WHERE id=?',
                                              (grant['id'],)).fetchone()[0])
        assert proof['issuer']['user_id'] == 'reviewer'
        assert 'store_path' not in json.dumps([preview, grant])
        listed = invoke(surface, 'recovery', 'list_handoffs', {'source_task': value.task_id}, connection, temporary)
        assert [item['id'] for item in listed['handoffs']] == [grant['id']]
        assert invoke(surface, 'recovery', 'get_handoff', {'handoff_id': grant['id']},
                      connection, temporary)['handoff']['id'] == grant['id']
        result = invoke(surface, 'skill', operation, {**adoption, 'handoff_id': grant['id']}, connection, temporary)
        reviewed = (result['provenance']['completion_review'] if operation == 'record'
                    else result['publication']['completion_review'])
        assert reviewed['evidence_handoff']['id'] == grant['id'] and result['owner']['user_id'] == 'owner'
        assert runtime.get(value.task_id).state == 'paused'
        with pytest.raises(AgentTaskError):
            AgentRuntimeClient(connection).call('get', {'task_id': value.child_id})
        revoked = invoke(surface, 'recovery', 'revoke_handoff', {'handoff_id': grant['id']}, connection, temporary)
        assert revoked['handoff']['state'] == 'revoked'
    finally:
        server.stop()


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
@pytest.mark.parametrize('surface', SURFACES)
def test_shared_surfaces_record_the_actual_other_caller_reader_with_selected_consent(recording, surface,
                                                                                   monkeypatch, tmp_path):
    exercise(recording, surface, 'record', request_for(recording), monkeypatch, tmp_path)


@pytest.mark.parametrize('trial', ['named_caller'], indirect=True)
@pytest.mark.parametrize('surface', SURFACES)
def test_shared_surfaces_publish_the_original_trial_with_selected_other_caller_consent(trial, surface,
                                                                                    monkeypatch, tmp_path):
    exercise(trial, surface, 'accept', acceptance(trial), monkeypatch, tmp_path)
