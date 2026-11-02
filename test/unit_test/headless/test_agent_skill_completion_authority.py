"""Skill adoption keeps real owner/reviewer authority live through publication and transaction rollback."""
import json

import pytest

from headless.test_agent_skill_completion import acceptance, trial as _trial
from headless.test_agent_skill_completion_security import assert_unpublished
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rest_api.rest_server import RestApiServer

trial = _trial


@pytest.mark.parametrize('trial', ['named'], indirect=True)
def test_http_revoked_reviewer_is_typed_refusal_without_publication(trial, tmp_path):
    server = RestApiServer(port=0, token='owned-skill-authority', agent_runtime=trial.runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = tmp_path / 'connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': server.token}), encoding='utf-8')
        trial.users.remove_user('reviewer')
        with pytest.raises(AgentTaskError) as error:
            AgentRuntimeClient(connection).call('skill', {'operation': 'accept', 'request': acceptance(trial)})
        assert '(409)' in str(error.value)
        assert_unpublished(trial)
    finally:
        server.stop()


@pytest.mark.parametrize('trial', ['named'], indirect=True)
@pytest.mark.parametrize('change', ['owner', 'reviewer', 'reviewer_role'])
def test_current_authority_is_required_before_adoption(trial, change):
    if change == 'reviewer_role':
        trial.users.set_role('reviewer', 'operator')
    else:
        trial.users.remove_user(change)
    with pytest.raises((AgentTaskError, AuthorizationError)):
        trial.runtime.skills.control('accept', acceptance(trial))
    assert_unpublished(trial)


@pytest.mark.parametrize('trial', ['named'], indirect=True)
def test_revocation_after_proof_rolls_back_publication_and_adoption(trial, monkeypatch):
    from je_auto_control.utils.agent_runtime.task_skills import AgentSkills
    check = AgentSkills._check_trial
    def revoked(connection, candidate, row):
        check(connection, candidate, row)
        trial.users.remove_user('reviewer')
    monkeypatch.setattr(AgentSkills, '_check_trial', staticmethod(revoked))
    with pytest.raises((AgentTaskError, AuthorizationError)):
        trial.runtime.skills.control('accept', acceptance(trial))
    assert_unpublished(trial)


@pytest.mark.parametrize('trial', ['named_caller'], indirect=True)
def test_source_owner_cannot_implicitly_read_an_existing_admin_owned_child(trial):
    with pytest.raises(AgentTaskError, match='another caller'):
        trial.runtime.skills.control('accept', acceptance(trial))
    assert_unpublished(trial)
