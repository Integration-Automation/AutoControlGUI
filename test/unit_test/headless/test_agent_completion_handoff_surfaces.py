"""Shared recovery surfaces expose an explicit bounded renewed-reader handoff review."""
import json

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal
from headless.test_agent_completion_handoff import completed as _completed, request_for
from headless.test_agent_evidence_handoff_surfaces import invoke
from je_auto_control.utils.rest_api.rest_server import RestApiServer
from je_auto_control.utils.rbac.authorization import authorization_scope

renewal = _renewal
completed = _completed


@pytest.mark.parametrize('renewal', ['named_dag'], indirect=True)
@pytest.mark.parametrize('surface', ['python', 'executor', 'cli', 'rest', 'mcp'])
def test_shared_surfaces_review_issue_inspect_and_revoke_the_exact_renewed_reader(completed, monkeypatch,
                                                                               tmp_path, surface):
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    assert 'AC_agent_task_recovery' in COMMAND_SPECS
    server = RestApiServer(port=0, token='owned-renewed-handoff-surfaces', agent_runtime=completed.runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = tmp_path / 'connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': server.token,
                                          'generation': 'owned-renewed-handoff-surfaces'}), encoding='utf-8')
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path', lambda: connection)
        with authorization_scope(completed.reviewer):
            preview = invoke(surface, connection, tmp_path, 'review_handoff', request_for(completed))
            assert preview['evidence']['completion_authorization']['completion_task'] == completed.child
            grant = invoke(surface, connection, tmp_path, 'create_handoff', {**request_for(completed),
                'review': preview['handoff_review'], 'note': 'Explicit current read-only evidence handoff'})['handoff']
        assert grant['evidence_only'] is True and grant['input_authorized'] is False
        listed = invoke(surface, connection, tmp_path, 'list_handoffs',
                        {'batch_id': completed.batch_id, 'node_id': 'a'})
        assert [item['id'] for item in listed['handoffs']] == [grant['id']]
        historical = invoke(surface, connection, tmp_path, 'get_handoff', {'handoff_id': grant['id']})
        assert historical['handoff']['id'] == grant['id']
        revoked = invoke(surface, connection, tmp_path, 'revoke_handoff', {'handoff_id': grant['id']})
        assert revoked['handoff']['state'] == 'revoked'
    finally:
        server.stop()
