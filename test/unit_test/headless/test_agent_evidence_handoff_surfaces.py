"""Existing shared recovery surfaces carry explicit evidence-only consent and revocation."""
import json

import pytest

from headless.test_agent_evidence_handoff import handoff as _handoff, request_for
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.rest_api.rest_server import RestApiServer
from je_auto_control.utils.rbac.authorization import authorization_scope

handoff = _handoff


def invoke(surface, connection, temporary, operation, request):
    import je_auto_control as ac
    from je_auto_control.cli import build_parser
    from je_auto_control.utils.agent_runtime.cli import run
    from je_auto_control.utils.tool_use_schema import run_tool_call
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    if surface == 'python':
        return ac.manage_agent_recovery(operation, request)
    if surface == 'executor':
        return run_tool_call('AC_agent_task_recovery', {'operation': operation, 'request': request})
    if surface == 'cli':
        path = temporary / 'handoff.json'
        path.write_text(json.dumps(request), encoding='utf-8')
        return run(build_parser().parse_args(['agent-task', 'recovery', operation, str(path)]))
    if surface == 'mcp':
        tool = next(item for item in build_default_tool_registry() if item.name == 'ac_agent_task_recovery')
        assert operation in tool.input_schema['properties']['operation']['enum']
        return tool.invoke({'operation': operation, 'request': request})
    return AgentRuntimeClient(connection).call('recovery', {'operation': operation, 'request': request})


@pytest.mark.parametrize('surface', ['python', 'executor', 'cli', 'rest', 'mcp'])
def test_shared_surfaces_review_issue_inspect_and_revoke_only_the_exact_handoff(handoff, monkeypatch, tmp_path,
                                                                            surface):
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    assert 'AC_agent_task_recovery' in COMMAND_SPECS
    server = RestApiServer(port=0, token='owned-handoff-surfaces', agent_runtime=handoff.runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = tmp_path / 'connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': server.token,
                                          'generation': 'owned-handoff-surfaces'}), encoding='utf-8')
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path', lambda: connection)
        with authorization_scope(handoff.reviewer):
            review = invoke(surface, connection, tmp_path, 'review_handoff', request_for(handoff))
            grant = invoke(surface, connection, tmp_path, 'create_handoff', {**request_for(handoff),
                'review': review['handoff_review'], 'note': 'Explicit immutable evidence-only consent'})['handoff']
        assert grant['evidence_only'] is True and grant['input_authorized'] is False
        assert invoke(surface, connection, tmp_path, 'get_handoff', {'handoff_id': grant['id']})['handoff'] == grant
        listed = invoke(surface, connection, tmp_path, 'list_handoffs', {'batch_id': handoff.batch_id, 'node_id': 'a'})
        assert [item['id'] for item in listed['handoffs']] == [grant['id']]
        revoked = invoke(surface, connection, tmp_path, 'revoke_handoff', {'handoff_id': grant['id']})
        assert revoked['handoff']['state'] == 'revoked'
        assert handoff.runtime.store.get(handoff.child)['owner']['user_id'] == 'reviewer'
    finally:
        server.stop()
