"""Task handoffs preserve real retention bounds, restart identity and sixteen-link limits."""
from types import SimpleNamespace
import time

import pytest

from headless.test_agent_task_handoff import recording as _recording, issue, no_helper
from headless.test_agent_skill_recording_completion import request_for
from headless.test_agent_completion_handoff import completed as _completed, renewal as _renewal
from headless.test_agent_completion_authorization import create
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, origin_policy
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.rbac.authorization import authorization_scope

recording = _recording
renewal = _renewal
completed = _completed


def another_reader(value, source, *, finish=False):
    runtime = value.runtime
    with authorization_scope(value.reviewer):
        preview = runtime.recovery.control('review_completion_authorization', {'task_id': source})
        child = runtime.recovery.control('create_authorized_completion', {
            'task_id': source, 'snapshot': preview['snapshot'],
            'authorization_review': preview['authorization_review'],
            'note': 'Explicitly reviewed another independent non-DAG read-only verification'})['task_id']
        if finish:
            assert runtime.finish(child).state == 'succeeded'
        else:
            runtime.pause(child)
    return child


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
def test_source_anchoring_at_a_later_reader_cannot_extend_an_expired_real_ancestor(recording):
    runtime = recording.runtime
    with runtime.store.connection(write=True) as connection:
        connection.execute('UPDATE agent_tasks SET updated=? WHERE id=?',
                           (time.time() - 31 * 86400, recording.child_id))
    second = another_reader(recording, recording.child_id)
    final = another_reader(recording, second, finish=True)
    with pytest.raises(AgentTaskError, match='expired'):
        issue(recording, second, final)
    with runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_task_handoffs').fetchone()[0] == 0


@pytest.mark.parametrize('recording', ['named_caller'], indirect=True)
def test_actual_grant_retry_and_other_caller_completion_survive_runtime_restart(recording, monkeypatch):
    runtime = recording.runtime
    grant = issue(recording, recording.task_id, recording.child_id)
    runtime.close()
    target = NativeDesktopTarget(resource_path=recording.manifest.parent / 'owned-input.lock')
    reopened = AgentRuntime(runtime.store.path, targets={'local-files': target})
    value = SimpleNamespace(runtime=reopened, reviewer=recording.reviewer)
    before = recording.manifest.read_bytes()
    try:
        monkeypatch.setattr(NativeDesktopTarget, '_launch', no_helper)
        assert issue(value, recording.task_id, recording.child_id)['id'] == grant['id']
        candidate = reopened.skills.control('record', request_for(recording, handoff_id=grant['id']))
        assert candidate['state'] == 'draft'
        assert candidate['provenance']['completion_review']['evidence_handoff']['id'] == grant['id']
        assert reopened.get(recording.task_id).state == 'paused' and recording.manifest.read_bytes() == before
        with pytest.raises(AgentTaskError, match='another caller'):
            reopened.get(recording.child_id)
    finally:
        reopened.close()


@pytest.mark.parametrize('renewal', ['named'], indirect=True)
def test_sixteen_real_renewed_readers_grant_completion_without_an_extra_link_or_input(completed, monkeypatch):
    runtime = completed.runtime
    parent = completed.child
    with authorization_scope(completed.reviewer):
        for index in range(2, 17):
            parent = create(completed, parent)
            if index < 16:
                runtime.pause(parent)
        assert runtime.finish(parent).state == 'succeeded'
        with pytest.raises(AgentTaskError, match='sixteen'):
            create(completed, parent)
    witness = origin_policy._path(completed.old.identifier).read_bytes()
    monkeypatch.setattr(NativeDesktopTarget, '_launch', no_helper)
    grant = issue(completed, completed.source, parent)
    access = runtime.recovery.task_handoff_evidence(completed.source, parent, grant['id'])
    assert len(access.links) == 16 and len(access.rows) == 17
    candidate = runtime.skills.control('record', {'task_id': completed.source, 'completion_task_id': parent,
        'handoff_id': grant['id'], 'name': 'Sixteen actual reviewed readers'})
    assert candidate['state'] == 'draft' and candidate['publication'] is None
    assert candidate['provenance']['completion_review']['task_id'] == parent
    assert runtime.get(completed.source).state == 'paused'
    assert origin_policy._path(completed.old.identifier).read_bytes() == witness
