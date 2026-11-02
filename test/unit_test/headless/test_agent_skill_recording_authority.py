"""Recording authority remains live through draft insertion and cannot transfer old reader ownership."""
import pytest

from headless.test_agent_skill_recording_completion import recording as _recording, request_for
from headless.test_agent_skill_recording_security import assert_no_draft
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.task_skills import AgentSkills
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope

recording = _recording


@pytest.mark.parametrize('recording', ['named'], indirect=True)
@pytest.mark.parametrize('change', ['owner', 'reviewer', 'reviewer_role'])
def test_live_source_owner_and_reviewer_are_required(recording, change):
    if change == 'reviewer_role':
        recording.users.set_role('reviewer', 'operator')
    else:
        recording.users.remove_user(change)
    with pytest.raises(AgentTaskError, match='authority changed'):
        recording.runtime.skills.control('record', request_for(recording))
    assert_no_draft(recording)


@pytest.mark.parametrize('recording', ['named'], indirect=True)
@pytest.mark.parametrize('principal', ['owner', 'reviewer'])
def test_revocation_after_draft_sql_rolls_back_recording(recording, monkeypatch, principal):
    insert = AgentSkills._insert_candidate
    def revoked(connection, candidate):
        identifier = insert(connection, candidate)
        recording.users.remove_user(principal)
        return identifier
    monkeypatch.setattr(AgentSkills, '_insert_candidate', staticmethod(revoked))
    with pytest.raises(AgentTaskError, match='authority changed'):
        recording.runtime.skills.control('record', request_for(recording))
    assert_no_draft(recording)


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
def test_source_owner_cannot_implicitly_adopt_an_admin_owned_reader(recording):
    with pytest.raises(AgentTaskError, match='another caller'):
        recording.runtime.skills.control('record', request_for(recording))
    assert_no_draft(recording)


@pytest.mark.parametrize('recording', ['named'], indirect=True)
def test_named_source_owner_records_only_owned_reader_provenance(recording):
    import json
    candidate = recording.runtime.skills.control('record', request_for(recording))
    assert candidate['owner']['user_id'] == 'owner'
    assert 'store_path' not in json.dumps(candidate['provenance']['completion_review'])


@pytest.mark.parametrize('recording', ['named'], indirect=True)
def test_separate_callers_revocation_after_insert_rolls_back_draft(recording, monkeypatch):
    recording.users.add_user(user_id='manager', display_name='Manager', role='admin')
    manager = AuthorizationContext('manager', 'admin', store_path=str(recording.users.path))
    insert = AgentSkills._insert_candidate
    def revoked(connection, candidate):
        identifier = insert(connection, candidate)
        recording.users.remove_user('manager')
        return identifier
    monkeypatch.setattr(AgentSkills, '_insert_candidate', staticmethod(revoked))
    with authorization_scope(manager), pytest.raises(AgentTaskError, match='authority changed'):
        recording.runtime.skills.control('record', request_for(recording))
    assert_no_draft(recording)
