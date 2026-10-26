"""Cold coordinator reopen must revalidate actual remote consent without refreshing its source expiry."""
from contextlib import contextmanager

import pytest

from headless.test_agent_transfer_adoption import review_adoption, approve, start, revoke
from headless.test_agent_transfer_evidence_remote import remote_recovery, grant
from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.dag_transfer_checks import DagTransferChecks


@contextmanager
def restart_case(tmp_path, monkeypatch, phase):
    with remote_recovery(tmp_path, monkeypatch) as value:
        identifier = grant(value)
        reviewed = review_adoption(value, identifier)
        approved = None
        if phase == 'provisional':
            with monkeypatch.context() as scoped:
                def interrupted(*_args):
                    raise RuntimeError('Owned interruption after durable provisional insertion')
                scoped.setattr(DagTransferChecks, 'finish', interrupted)
                with pytest.raises(RuntimeError, match='Owned interruption'):
                    approve(value, reviewed)
        else:
            approved = approve(value, reviewed)
        with value.coordinator.store.connection() as database:
            stored = dict(database.execute('SELECT id,state FROM agent_dag_approvals').fetchone())
        assert stored['state'] == phase
        with value.runtime.store.connection() as database:
            expires = value.runtime.transfers.source.records.find(database, identifier)['expires']
        path = value.coordinator.store.path
        value.coordinator.close()
        value.coordinator = AgentRuntime(path, targets={})
        try:
            yield value, identifier, reviewed, approved, stored, expires
        finally:
            value.coordinator.close()


def invalidate(value, identifier, change):
    if change == 'grant':
        revoke(value, identifier)
    elif change == 'expiry':
        with value.runtime.store.connection(write=True) as database:
            database.execute('UPDATE agent_transfer_grants SET expires=0 WHERE id=?', (identifier,))
    elif change == 'host':
        replacement = value.users.rotate_token('owner')
        admin_client._default_console.add_host('source', value.server.base_url, replacement)
    elif change == 'unavailable':
        value.server.stop()


@pytest.mark.parametrize('phase', ['provisional', 'ready'])
@pytest.mark.parametrize('change', ['none', 'grant', 'expiry', 'host', 'unavailable'])
def test_actual_coordinator_reopen_preserves_consent_identity_and_revalidates_remote_authority(
        tmp_path, monkeypatch, phase, change):
    with restart_case(tmp_path, monkeypatch, phase) as case:
        value, identifier, reviewed, approved, stored, expires = case
        actions = value.runtime.store.actions(value.child)
        invalidate(value, identifier, change)
        if change == 'none':
            if phase == 'provisional':
                approved = approve(value, reviewed)
            assert approved['approval_id'] == stored['id'] and approved['approval_state'] == 'ready'
            running = start(value, reviewed, approved)
            result = value.coordinator.batches.control('validate_node', {'batch_id': reviewed['batch_id'],
                'node_id': 'remote-file', 'attempt': running['attempt']})
            assert result['outcome'] == 'completed' and result['task_id'] == value.child
            with value.runtime.store.connection() as database:
                record = value.runtime.transfers.source.records.find(database, identifier)
            assert record['expires'] == expires, 'Coordinator restart cannot renew the source evidence deadline'
        else:
            with pytest.raises(AgentTaskError):
                if phase == 'provisional':
                    approve(value, reviewed)
                else:
                    start(value, reviewed, approved)
            with value.coordinator.store.connection() as database:
                assert database.execute('SELECT state FROM agent_dag_batches').fetchone()[0] != 'running'
        with value.coordinator.store.connection() as database:
            assert database.execute('SELECT count(*) FROM agent_dag_approvals').fetchone()[0] == 1
        assert value.coordinator.list() == [] and value.runtime.store.actions(value.child) == actions
        assert value.output.read_bytes() == value.body
