"""A genuine coordinator adopts only live separately granted remote recovery evidence."""
from contextlib import contextmanager
from copy import deepcopy
import sqlite3

import pytest

from headless.test_agent_transfer_evidence_remote import remote_recovery, grant
from headless.test_agent_transfer_peer_security import post
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.dag_transfer_checks import DagTransferChecks
from je_auto_control.utils.dag.batch_contract import bind_definition
from je_auto_control.utils.agent_runtime.dag_batches import DagBatches
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.dag import managed_tasks
from je_auto_control.utils.rbac.authorization import authorization_scope


def review_adoption(value, identifier):
    tag = value.runtime.store.get(value.source)['spec']['options']['dag_batch']
    batch = value.coordinator.batches.control('get', {'batch_id': tag['batch_id']})
    value.coordinator.batches.control('pause_batch', {'batch_id': tag['batch_id']})
    decision = {'node_id': tag['node_id'], 'action': 'successor', 'task_id': value.child, 'handoff_id': identifier}
    decisions = [decision]
    bound = bind_definition(batch['definition'], tag['batch_id'], batch['graph_hash'])
    decisions += [{'node_id': node['id'], 'action': 'dispatch', 'spec': node['task']['spec']}
                  for node in bound['nodes'] if node['id'] != tag['node_id']]
    reviewed = value.coordinator.batches.control('review_continuation', {'batch_id': tag['batch_id'],
        'definition': batch['input_definition'], 'decisions': decisions})
    assert reviewed['can_approve'], reviewed['nodes']
    return reviewed


def approve(value, reviewed):
    return value.coordinator.batches.control('approve_continuation', {
        **{name: reviewed[name] for name in ('batch_id', 'definition', 'snapshot', 'decisions')},
        'note': 'Approve only the original node and this live remote proof'})


def start(value, reviewed, approval):
    return value.coordinator.batches.control('start_continuation', {'batch_id': reviewed['batch_id'],
        'definition': reviewed['definition'], 'approval_id': approval['approval_id'], 'max_parallel': 1})


def revoke(value, identifier):
    status, reply = post(value.server, '/agent/transfer', {'operation': 'revoke_evidence',
        'request': {'grant_id': identifier}}, token=value.owner_token)
    assert status == 200, reply


def test_actual_coordinator_adopts_another_remote_owners_leaf_without_read_or_input_authority(tmp_path, monkeypatch):
    with remote_recovery(tmp_path, monkeypatch) as value:
        identifier = grant(value)
        before = value.runtime.store.actions(value.child)
        reviewed = review_adoption(value, identifier)
        approved = approve(value, reviewed)
        assert approved['approval_state'] == 'ready'
        running = start(value, reviewed, approved)
        result = value.coordinator.batches.control('validate_node', {'batch_id': reviewed['batch_id'],
            'node_id': 'remote-file', 'attempt': running['attempt']})
        assert result['outcome'] == 'completed' and result['task_id'] == value.child
        with authorization_scope(value.owner), pytest.raises(AgentTaskError, match='another caller'):
            value.runtime.get(value.child)
        assert value.runtime.store.actions(value.child) == before
        assert value.output.read_bytes() == value.body
        assert value.coordinator.list() == []
        revoke(value, identifier)
        with pytest.raises(AgentTaskError):
            value.coordinator.batches.control('validate_node', {'batch_id': reviewed['batch_id'],
                'node_id': 'remote-file', 'attempt': running['attempt']})


@pytest.mark.parametrize('phase', ['provisional', 'starting'])
@pytest.mark.parametrize('change', ['grant', 'issuer_role', 'expiry', 'unavailable'])
def test_source_authority_loss_after_provisional_write_prevents_approval_or_start(tmp_path, monkeypatch, phase, change):
    with remote_recovery(tmp_path, monkeypatch) as value:
        identifier = grant(value)
        reviewed = review_adoption(value, identifier)
        approved = approve(value, reviewed) if phase == 'starting' else None
        original = DagTransferChecks.finish
        def finish(checks, approval_id, pending, commit):
            assert pending == phase
            with value.coordinator.store.connection() as connection:
                row = connection.execute('SELECT state FROM agent_dag_approvals WHERE id=?',
                                         (approval_id,)).fetchone()
                assert row['state'] == phase
                assert connection.execute('SELECT state FROM agent_dag_batches').fetchone()[0] != 'running'
                if phase == 'provisional':
                    assert connection.execute('SELECT count(*) FROM agent_dag_adoptions').fetchone()[0] == 0
            if change == 'grant':
                revoke(value, identifier)
            elif change == 'issuer_role':
                value.users.set_role('reviewer', 'viewer')
            elif change == 'expiry':
                with value.runtime.store.connection(write=True) as connection:
                    connection.execute('UPDATE agent_transfer_grants SET expires=0 WHERE id=?', (identifier,))
            else:
                value.server.stop()
            return original(checks, approval_id, pending, commit)
        monkeypatch.setattr(DagTransferChecks, 'finish', finish)
        with pytest.raises(AgentTaskError):
            if phase == 'provisional':
                approve(value, reviewed)
            else:
                start(value, reviewed, approved)
        with value.coordinator.store.connection() as connection:
            assert connection.execute('SELECT state FROM agent_dag_approvals').fetchone()[0] == 'cancelled'
            assert connection.execute('SELECT state FROM agent_dag_batches').fetchone()[0] == 'waiting_review'
        assert value.runtime.store.actions(value.child)


def test_revoke_between_downstream_claim_and_return_never_authorizes_dispatch(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import dag_batches
    with remote_recovery(tmp_path, monkeypatch, dependent=True) as value:
        identifier = grant(value)
        reviewed = review_adoption(value, identifier)
        running = start(value, reviewed, approve(value, reviewed))
        original = dag_batches.claim_node
        def claim(connection, batch, request):
            original(connection, batch, request)
            revoke(value, identifier)
        monkeypatch.setattr(dag_batches, 'claim_node', claim)
        with pytest.raises(AgentTaskError):
            value.coordinator.batches.control('claim', {'batch_id': reviewed['batch_id'],
                'attempt': running['attempt'], 'node_id': 'downstream'})
        status, absent = post(value.server, '/agent/lookup', {'idempotency_key': next(
            node['task']['idempotency_key'] for node in running['definition']['nodes'] if node['id'] == 'downstream')},
            token=value.owner_token)
        assert status == 200 and absent['found'] is False


@pytest.mark.parametrize('lost_ack', [False, True])
def test_revoked_dependency_pauses_only_the_actual_already_dispatched_downstream_task(tmp_path, monkeypatch, lost_ack):
    with remote_recovery(tmp_path, monkeypatch, dependent=True) as value:
        identifier = grant(value)
        reviewed = review_adoption(value, identifier)
        running = start(value, reviewed, approve(value, reviewed))
        value.coordinator.batches.control('claim', {'batch_id': reviewed['batch_id'],
            'attempt': running['attempt'], 'node_id': 'downstream'})
        task = next(node['task'] for node in running['definition']['nodes'] if node['id'] == 'downstream')
        status, accepted = post(value.server, '/agent/submit', {key: task[key]
            for key in ('spec', 'idempotency_key')}, token=value.owner_token)
        assert status == 200, accepted
        unrelated = deepcopy(task['spec'])
        unrelated['options'].pop('dag_batch')
        status, independent = post(value.server, '/agent/submit', {'spec': unrelated,
            'idempotency_key': 'independent-owned-user-task'}, token=value.owner_token)
        assert status == 200, independent
        previous = value.runtime.store.get(independent['task_id'])['state']
        if lost_ack:
            original = managed_tasks.bound_task_connection
            def connection(host, binding):
                call = original(host, binding)
                def reply(operation, body, timeout):
                    result = call(operation, body, timeout)
                    if operation == 'pause':
                        raise OSError('owned acknowledgement lost after actual pause')
                    return result
                return reply
            monkeypatch.setattr(managed_tasks, 'bound_task_connection', connection)
        revoke(value, identifier)
        with pytest.raises(AgentTaskError):
            value.coordinator.batches.control('validate_node', {'batch_id': reviewed['batch_id'],
                'attempt': running['attempt'], 'node_id': 'remote-file'})
        with authorization_scope(value.owner):
            assert value.runtime.get(accepted['task_id']).state == 'paused'
        batch = value.coordinator.batches.control('get', {'batch_id': reviewed['batch_id']})
        assert batch['state'] == 'waiting_review'
        dependent = next(node for node in batch['nodes'] if node['id'] == 'downstream')
        assert dependent['phase'] == 'unknown'
        assert dependent['receipt'] == {'outcome': 'requires_review', 'task_id': accepted['task_id']}
        assert value.runtime.store.get(independent['task_id'])['state'] == previous


@pytest.mark.parametrize('phase', ['provisional', 'starting'])
def test_pending_remote_confirmation_retains_the_exact_runtime_owner_until_it_finishes(tmp_path, monkeypatch, phase):
    with remote_recovery(tmp_path, monkeypatch) as value:
        identifier = grant(value)
        reviewed = review_adoption(value, identifier)
        approved = approve(value, reviewed) if phase == 'starting' else None
        original = DagTransferChecks.finish
        def finish(checks, approval_id, pending, commit):
            with pytest.raises(AgentTaskError, match='active transfer'):
                value.coordinator.close()
            return original(checks, approval_id, pending, commit)
        monkeypatch.setattr(DagTransferChecks, 'finish', finish)
        if phase == 'provisional':
            assert approve(value, reviewed)['approval_state'] == 'ready'
        else:
            assert start(value, reviewed, approved)['attempt']


def test_remote_confirmation_never_holds_the_coordinator_writer_during_peer_reads(tmp_path, monkeypatch):
    with remote_recovery(tmp_path, monkeypatch) as value:
        observed = set()
        original = DagBatches.transfer_call
        def transfer(batches, host, binding, path, body, timeout):
            if batches.runtime is value.coordinator and path == '/agent/transfer/peer':
                with value.coordinator.store.connection() as connection:
                    pending = connection.execute("SELECT state FROM agent_dag_approvals "
                                                 "WHERE state IN ('provisional','starting')").fetchone()
                if pending is not None:
                    with sqlite3.connect(value.coordinator.store.path, timeout=0) as writing:
                        writing.execute('BEGIN EXCLUSIVE')
                        writing.rollback()
                    observed.add(pending['state'])
            return original(batches, host, binding, path, body, timeout)
        monkeypatch.setattr(DagBatches, 'transfer_call', transfer)
        reviewed = review_adoption(value, grant(value))
        start(value, reviewed, approve(value, reviewed))
        assert observed == {'provisional', 'starting'}


def test_interrupted_provisional_approval_resumes_only_its_exact_explicit_request(tmp_path, monkeypatch):
    with remote_recovery(tmp_path, monkeypatch) as value:
        reviewed = review_adoption(value, grant(value))
        with monkeypatch.context() as scoped:
            def interrupted(*_args):
                raise RuntimeError('owned interruption after durable provisional insertion')
            scoped.setattr(DagTransferChecks, 'finish', interrupted)
            with pytest.raises(RuntimeError, match='owned interruption'):
                approve(value, reviewed)
        with value.coordinator.store.connection() as connection:
            original = dict(connection.execute('SELECT id,state FROM agent_dag_approvals').fetchone())
            assert original['state'] == 'provisional'
            assert connection.execute('SELECT count(*) FROM agent_dag_adoptions').fetchone()[0] == 0
        approved = approve(value, reviewed)
        assert approved['approval_id'] == original['id'] and approved['approval_state'] == 'ready'
        with value.coordinator.store.connection() as connection:
            assert connection.execute('SELECT count(*) FROM agent_dag_approvals').fetchone()[0] == 1


@pytest.mark.parametrize('phase', ['provisional', 'starting'])
def test_stop_all_cancels_pending_remote_consent_before_it_can_publish_an_attempt(tmp_path, monkeypatch, phase):
    with remote_recovery(tmp_path, monkeypatch) as value:
        reviewed = review_adoption(value, grant(value))
        approved = approve(value, reviewed) if phase == 'starting' else None
        original = DagTransferChecks.finish
        def finish(checks, identifier, pending, commit):
            value.coordinator.batches.stop_all()
            return original(checks, identifier, pending, commit)
        monkeypatch.setattr(DagTransferChecks, 'finish', finish)
        with pytest.raises(AgentTaskError):
            if phase == 'provisional':
                approve(value, reviewed)
            else:
                start(value, reviewed, approved)
        with value.coordinator.store.connection() as connection:
            assert connection.execute('SELECT state FROM agent_dag_approvals').fetchone()[0] == 'cancelled'
            assert connection.execute('SELECT state FROM agent_dag_batches').fetchone()[0] == 'waiting_review'


def complete_dependent(value, reviewed, running):
    value.coordinator.batches.control('claim', {'batch_id': reviewed['batch_id'],
        'attempt': running['attempt'], 'node_id': 'downstream'})
    task = next(node['task'] for node in running['definition']['nodes'] if node['id'] == 'downstream')
    status, accepted = post(value.server, '/agent/submit', {name: task[name]
        for name in ('spec', 'idempotency_key')}, token=value.owner_token)
    assert status == 200, accepted
    with authorization_scope(value.owner):
        assert run_task(value.runtime, accepted['task_id']).state == 'succeeded'
    return accepted['task_id']


@pytest.mark.parametrize('boundary', ['record', 'finish'])
def test_revoke_at_downstream_completion_commit_cannot_publish_a_successful_batch(tmp_path, monkeypatch, boundary):
    from je_auto_control.utils.agent_runtime import dag_batches
    with remote_recovery(tmp_path, monkeypatch, dependent=True) as value:
        identifier = grant(value)
        reviewed = review_adoption(value, identifier)
        running = start(value, reviewed, approve(value, reviewed))
        task_id = complete_dependent(value, reviewed, running)
        request = {'batch_id': reviewed['batch_id'], 'attempt': running['attempt'], 'node_id': 'downstream',
                   'receipt': {'outcome': 'completed', 'task_id': task_id}}
        if boundary == 'record':
            original = dag_batches.record_node
            def record(connection, batch, value):
                original(connection, batch, value)
                revoke(owner, identifier)
            owner = value
            monkeypatch.setattr(dag_batches, 'record_node', record)
        else:
            value.coordinator.batches.control('record', request)
            original = value.coordinator.store.connection
            triggered = []
            @contextmanager
            def connection(*, write=False):
                with original(write=write) as active:
                    yield active
                if write and not triggered:
                    with original() as reading:
                        state = reading.execute('SELECT state FROM agent_dag_batches').fetchone()[0]
                    if state == 'succeeded':
                        triggered.append(True)
                        revoke(value, identifier)
            monkeypatch.setattr(value.coordinator.store, 'connection', connection)
        with pytest.raises(AgentTaskError):
            value.coordinator.batches.control(boundary, request if boundary == 'record' else {
                'batch_id': reviewed['batch_id'], 'attempt': running['attempt']})
        result = value.coordinator.batches.control('get', {'batch_id': reviewed['batch_id']})
        assert result['state'] == 'waiting_review'
        assert value.runtime.store.get(task_id)['state'] == 'succeeded'


@pytest.mark.parametrize('change', ['hosts', 'details'])
def test_provisional_confirmation_refuses_replaced_local_approval_or_host_snapshot(tmp_path, monkeypatch, change):
    with remote_recovery(tmp_path, monkeypatch) as value:
        reviewed = review_adoption(value, grant(value))
        original = DagTransferChecks.finish
        def finish(checks, identifier, pending, commit):
            with value.coordinator.store.connection(write=True) as connection:
                if change == 'hosts':
                    connection.execute("UPDATE agent_dag_batches SET hosts='{}'")
                else:
                    connection.execute("UPDATE agent_dag_approvals SET details='{}' WHERE id=?", (identifier,))
            return original(checks, identifier, pending, commit)
        monkeypatch.setattr(DagTransferChecks, 'finish', finish)
        with pytest.raises(AgentTaskError):
            approve(value, reviewed)
        with value.coordinator.store.connection() as connection:
            assert connection.execute('SELECT count(*) FROM agent_dag_adoptions').fetchone()[0] == 0
