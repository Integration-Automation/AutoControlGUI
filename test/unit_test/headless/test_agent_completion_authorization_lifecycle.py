"""Renewal remains durable and bounded across retries, restarts and actual read-only lineage."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from headless.test_agent_completion_authorization import renewal as _renewal, reviewed, create
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, origin_policy

renewal = _renewal


def test_concurrent_retries_create_exactly_one_private_reader(renewal):
    _preview, request = reviewed(renewal)
    def approved(_index):
        with origin_policy.origin_scope(renewal.current.identifier):
            return renewal.runtime.recovery.control('create_authorized_completion', request)['task_id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        identifiers = list(pool.map(approved, range(2)))
    assert identifiers[0] == identifiers[1]
    assert renewal.runtime.store.actions(identifiers[0]) == []
    assert len(renewal.runtime.list()) == 2


def test_private_renewal_survives_runtime_restart_with_the_same_readonly_limits(renewal):
    child = create(renewal)
    runtime = renewal.runtime
    runtime.close()
    reopened = AgentRuntime(runtime.store.path, targets={'local-files': renewal.target})
    try:
        assert reopened.finish(child).state == 'succeeded'
        assert reopened.store.get(child)['spec']['roots'] == [str(renewal.reports)]
        assert reopened.store.actions(child) == [] and reopened.get(renewal.source).state == 'paused'
    finally:
        reopened.close()


def test_sixteen_real_readonly_links_succeed_and_a_seventeenth_is_refused(renewal):
    parent = renewal.source
    for index in range(16):
        parent = create(renewal, parent)
        if index < 15:
            renewal.runtime.pause(parent)
    assert renewal.runtime.finish(parent).state == 'succeeded'
    with pytest.raises(AgentTaskError, match='sixteen'):
        reviewed(renewal, parent)
    assert renewal.runtime.store.actions(parent) == [] and len(renewal.runtime.list()) == 17


def test_source_change_inside_final_completion_sql_cannot_publish_stale_success(renewal):
    child = create(renewal)
    with renewal.runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER owned_finish_change AFTER INSERT ON agent_completion "
            "BEGIN UPDATE agent_tasks SET reason='source changed during final SQL' "
            "WHERE id=(SELECT source_task FROM agent_task_recoveries WHERE task_id=NEW.task_id); END")
    with pytest.raises(AgentTaskError, match='snapshot'):
        renewal.runtime.finish(child)
    assert renewal.runtime.get(child).state != 'succeeded'
    assert renewal.runtime.get(child).metadata['completion_contract'] == 0
    assert renewal.runtime.store.get(renewal.source)['reason'] != 'source changed during final SQL'
