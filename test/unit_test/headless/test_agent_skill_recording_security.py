"""Stopped-source recording rejects stale or unowned proof and rolls back failed admission."""
from contextlib import contextmanager
import json

import pytest

from headless.test_agent_skill_recording_completion import recording as _recording, request_for
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.task_skills import AgentSkills

recording = _recording


def assert_no_draft(value):
    with value.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_candidates').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_publications').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM agent_skill_trials').fetchone()[0] == 0


@pytest.mark.parametrize('damage', ['binding', 'source_snapshot', 'unknown_effect', 'reports', 'retirement'])
def test_damaged_completion_cannot_leave_a_recorded_draft(recording, damage):
    changes = {
        'binding': ('DELETE FROM agent_readonly_completions WHERE task_id=?', (recording.child_id,)),
        'source_snapshot': ('UPDATE agent_tasks SET reason=? WHERE id=?', ('changed', recording.task_id)),
        'unknown_effect': ('UPDATE agent_actions SET status=? WHERE task_id=?', ('uncertain', recording.task_id)),
        'reports': ('UPDATE agent_tasks SET verification=? WHERE id=?', ('[]', recording.child_id)),
        'retirement': ('DELETE FROM agent_completion WHERE task_id=?', (recording.child_id,)),
    }
    with recording.runtime.store.connection(write=True) as connection:
        connection.execute(*changes[damage])
    with pytest.raises(AgentTaskError):
        recording.runtime.skills.control('record', request_for(recording))
    assert_no_draft(recording)


@pytest.mark.parametrize('identifier', [None, [], '', 'missing-completion'])
def test_invalid_reader_identity_creates_no_draft(recording, identifier):
    with pytest.raises(AgentTaskError):
        recording.runtime.skills.control('record', request_for(recording, completion_task_id=identifier))
    assert_no_draft(recording)


@pytest.mark.parametrize('which', ['task_id', 'child_id'])
def test_unwinding_source_or_reader_cannot_be_recorded(recording, which):
    identifier = getattr(recording, which)
    recording.runtime._executing.add(identifier)
    try:
        with pytest.raises(AgentTaskError):
            recording.runtime.skills.control('record', request_for(recording))
        assert_no_draft(recording)
    finally:
        recording.runtime._executing.discard(identifier)


def test_recording_without_host_completion_callbacks_refuses_before_writing(recording):
    with pytest.raises(AgentTaskError, match='completion provider'):
        AgentSkills(recording.runtime).control('record', request_for(recording))
    assert_no_draft(recording)


def test_source_changed_before_writer_admission_cannot_leave_a_stale_draft(recording, monkeypatch):
    original = recording.runtime.store.connection
    armed = [True]
    @contextmanager
    def changed(*, write=False):
        if write and armed[0]:
            armed[0] = False
            with original(write=True) as connection:
                connection.execute('UPDATE agent_tasks SET reason=? WHERE id=?', ('new review', recording.task_id))
        with original(write=write) as connection:
            yield connection
    monkeypatch.setattr(recording.runtime.store, 'connection', changed)
    with pytest.raises(AgentTaskError, match='snapshot'):
        recording.runtime.skills.control('record', request_for(recording))
    assert_no_draft(recording)


def test_forged_options_and_success_do_not_grant_recording_provenance(recording):
    runtime = recording.runtime
    spec = runtime.store.get(recording.child_id)['spec']
    spec['options']['completion_review'] = {'effect_task': recording.task_id}
    forged = runtime.submit(spec)
    reports = runtime.store.get(recording.child_id)['verification']
    runtime.store.update(forged.task_id, 'succeeded', verification=reports)
    with pytest.raises(AgentTaskError, match='private reviewed'):
        runtime.skills.control('record', request_for(recording, completion_task_id=forged.task_id))
    assert_no_draft(recording)


def test_malformed_private_binding_returns_typed_refusal_without_a_draft(recording):
    with recording.runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_readonly_completions SET details=? WHERE task_id=?',
                           (json.dumps({'contract': 1}), recording.child_id))
    with pytest.raises(AgentTaskError):
        recording.runtime.skills.control('record', request_for(recording))
    assert_no_draft(recording)


def test_unrelated_source_cannot_borrow_a_real_readers_evidence(recording):
    runtime = recording.runtime
    other = runtime.submit(runtime.store.get(recording.task_id)['spec'])
    with pytest.raises(AgentTaskError, match='original workflow'):
        runtime.skills.control('record', request_for(recording, task_id=other.task_id))
    assert_no_draft(recording)


@pytest.mark.parametrize('recording', ['origin'], indirect=True)
def test_expired_source_scope_cannot_be_renewed_by_recording(recording):
    recording.origin.revoke()
    with pytest.raises(AgentTaskError):
        recording.runtime.skills.control('record', request_for(recording))
    assert_no_draft(recording)
