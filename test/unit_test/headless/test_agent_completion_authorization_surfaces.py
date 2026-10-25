"""All shared recovery surfaces explicitly renew the same named-owner read-only completion scope."""
import json

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal
from headless.test_agent_evidence_handoff_surfaces import invoke
from je_auto_control.utils.rest_api.rest_server import RestApiServer

renewal = _renewal


@pytest.mark.parametrize('renewal', ['named'], indirect=True)
@pytest.mark.parametrize('surface', ['python', 'executor', 'cli', 'rest', 'mcp'])
def test_shared_surfaces_renew_only_the_reviewed_independent_completion(renewal, monkeypatch, tmp_path, surface):
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    assert 'AC_agent_task_recovery' in COMMAND_SPECS
    server = RestApiServer(port=0, token='owned-completion-renewal-surfaces', agent_runtime=renewal.runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = tmp_path / 'connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': server.token,
                                          'generation': 'owned-completion-renewal-surfaces'}), encoding='utf-8')
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path', lambda: connection)
        preview = invoke(surface, connection, tmp_path, 'review_completion_authorization', {'task_id': renewal.source})
        assert preview['verification_spec']['roots'] == [str(renewal.reports)]
        request = {'task_id': renewal.source, 'snapshot': preview['snapshot'],
                   'authorization_review': preview['authorization_review'], 'note': 'Reviewed this exact file scope'}
        child = invoke(surface, connection, tmp_path, 'create_authorized_completion', request)['task_id']
        assert renewal.runtime.finish(child).state == 'succeeded'
        metadata = renewal.runtime.get(child).metadata
        assert metadata['completion_contract'] == 1
        assert metadata['recovery']['reauthorization']['actor'] == 'owner'
        assert renewal.runtime.store.actions(child) == [] and renewal.runtime.get(renewal.source).state == 'paused'
    finally:
        server.stop()
