"""Completion handoffs retain actual input-recovery ancestry without treating inherited tags as admission."""
import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, create
from headless.test_agent_completion_handoff import issue
from je_auto_control.utils.rbac.authorization import authorization_scope

renewal = _renewal


@pytest.fixture
def mixed(renewal, monkeypatch):
    runtime = renewal.runtime
    with authorization_scope(renewal.reviewer):
        preview = runtime.recovery.control('review_authorization', {'task_id': renewal.source})
        assert preview['draft']['actions'] == [renewal.remaining_action]
        renewal.execution_child = runtime.recovery.control('create_authorized', {
            'task_id': renewal.source, 'snapshot': preview['snapshot'], 'spec': preview['draft'],
            'authorization_review': preview['authorization_review'],
            'note': 'Explicit fresh input consent for only the remaining owned-file manifest'})['task_id']
        for method, function in renewal.original_methods.items():
            monkeypatch.setattr(renewal.target, method, function)
        frame = runtime.observe(renewal.execution_child)
        runtime.act(renewal.execution_child, {**renewal.remaining_action, 'observation_id': frame.observation_id})
        runtime.pause(renewal.execution_child)
        def forbidden(*_args, **_kwargs):
            raise AssertionError('Completion and handoff may not replay an ordinary helper')
        for method in renewal.original_methods:
            monkeypatch.setattr(renewal.target, method, forbidden)
        renewal.child = create(renewal, renewal.execution_child)
        assert runtime.finish(renewal.child).state == 'succeeded'
    return renewal


@pytest.mark.parametrize('renewal', ['named_dag_partial'], indirect=True)
def test_mixed_executable_and_renewed_reader_chain_adopts_all_original_confirmed_effects(mixed):
    _review, _request, grant = issue(mixed)
    reply, chain = mixed.runtime.recovery.handoff_evidence(mixed.batch_id, 'a', mixed.source,
                                                         mixed.child, grant['id'])
    assert reply['state'] == 'succeeded' and len(chain) == 2
    assert len(mixed.runtime.store.actions(mixed.source)) == 1
    assert len(mixed.runtime.store.actions(mixed.execution_child)) == 1
    assert mixed.runtime.store.actions(mixed.child) == []
    assert mixed.runtime.get(mixed.source).state == 'paused'
    assert mixed.runtime.store.get(mixed.execution_child)['state'] == 'paused'
    with mixed.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_dag_local_tasks').fetchone()[0] == 1
