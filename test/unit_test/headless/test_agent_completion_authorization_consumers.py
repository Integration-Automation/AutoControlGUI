"""Renewed independent evidence remains revocable and records only a newly scoped skill draft."""
from contextvars import Context

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, create
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.completion_contract import validate_recorded_completion
from je_auto_control.utils.agent_runtime.runner import run_task

renewal = _renewal


def test_historical_get_cannot_attest_live_completion_after_issuing_origin_is_revoked(renewal):
    child = create(renewal)
    assert renewal.runtime.finish(child).state == 'succeeded'
    renewal.current.revoke()
    result = Context().run(renewal.runtime.get, child)
    assert result.state == 'succeeded'
    assert result.metadata['completion_contract'] == 0
    with pytest.raises(AgentTaskError, match='retirement contract'):
        validate_recorded_completion(result.to_dict(), renewal.runtime.store.get(renewal.source)['spec'])


def test_recording_uses_reviewed_scope_and_still_requires_its_own_fresh_validation(renewal, monkeypatch):
    child = create(renewal)
    assert renewal.runtime.finish(child).state == 'succeeded'
    before = renewal.manifest.read_bytes()
    candidate = renewal.runtime.skills.control('record', {'task_id': renewal.source,
        'completion_task_id': child, 'name': 'Explicitly renewed file workflow'})
    assert candidate['state'] == 'draft' and candidate['version'] == 0
    assert candidate['spec']['roots'] == [str(renewal.reports)]
    assert candidate['spec']['actions'] == [renewal.action]
    assert renewal.old.identifier not in candidate['spec']['options']['origin_policies']
    assert renewal.current.identifier in candidate['spec']['options']['origin_policies']
    assert renewal.manifest.read_bytes() == before
    assert candidate['provenance']['completion_review']['task_id'] == child
    with pytest.raises(AgentTaskError):
        renewal.runtime.skills.control('accept', {'candidate_id': candidate['id'], 'task_id': child,
            'expected_version': 0, 'note': 'A reader cannot substitute the new draft validation trial'})
    for method, function in renewal.original_methods.items():
        monkeypatch.setattr(renewal.target, method, function)
    trial = renewal.runtime.skills.control('validate', {'candidate_id': candidate['id']})
    assert run_task(renewal.runtime, trial['task_id']).state == 'succeeded'
    accepted = renewal.runtime.skills.control('accept', {'candidate_id': candidate['id'], 'task_id': trial['task_id'],
        'expected_version': 0, 'note': 'Accepted only the separately executed current-scope trial'})
    assert accepted['version'] == 1 and renewal.runtime.get(renewal.source).state == 'paused'
