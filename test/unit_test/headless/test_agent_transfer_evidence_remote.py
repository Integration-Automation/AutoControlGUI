"""Actual coordinator requests reach a named remote owner; portable proof leaves its private stores local."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from headless.test_agent_transfer_source import completed_source
from headless.test_agent_transfer_source_lineage import recover_nodes
from headless.test_agent_transfer_evidence import evidence_server, evidence_review, evidence_create, actual_binding
from headless.test_agent_transfer_peer_security import post
from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_evidence import resolve_remote_evidence
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


@contextmanager
def remote_recovery(tmp_path, monkeypatch, *, dependent=False):
    source_root = tmp_path / 'source'
    source_root.mkdir()
    with completed_source(source_root, named=True) as (runtime, _initial, output, body, users):
        owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
        reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
        with evidence_server(runtime, users) as server:
            owner_token, reviewer_token = users.rotate_token('owner'), users.rotate_token('reviewer')
            book = admin_client.AdminConsoleClient(persist_path=tmp_path / 'coordinator-hosts.json')
            book.add_host('source', server.base_url, owner_token)
            monkeypatch.setattr(admin_client, '_default_console', book)
            coordinator = AgentRuntime(tmp_path / 'coordinator.sqlite3', targets={})
            try:
                action = {'tool': 'AC_workflow_manifest', 'arguments': {'directory': str(source_root),
                    'path': str(source_root / 'actual-manifest.json'), 'names': [output.name]}}
                definition = {'nodes': [{'id': 'remote-file', 'host': 'source', 'task': {
                    'spec': {'goal': 'verify the actual remote file', 'target': 'local-files', 'mode': 'skill',
                        'roots': [str(source_root)], 'allowed_tools': ['AC_workflow_manifest'], 'actions': [action],
                        'success_criteria': [{'kind': 'actions_complete'},
                                             {'kind': 'file_exists', 'path': str(output)}]},
                    'idempotency_key': 'original-remote-evidence', 'wait_seconds': 20}}]}
                if dependent:
                    downstream = deepcopy(definition['nodes'][0]['task'])
                    downstream['idempotency_key'] = 'original-downstream-evidence'
                    downstream['spec']['actions'][0]['arguments']['path'] = str(
                        source_root / 'downstream-manifest.json')
                    definition['nodes'].append({'id': 'downstream', 'host': 'source',
                                                'depends_on': ['remote-file'], 'task': downstream})
                registered = coordinator.batches.control('register', {'definition': definition, 'max_parallel': 1})
                started = coordinator.batches.control('begin', {'batch_id': registered['batch_id'],
                    'definition': definition, 'max_parallel': 1})
                coordinator.batches.control('claim', {'batch_id': registered['batch_id'],
                    'attempt': started['attempt'], 'node_id': 'remote-file'})
                request = next(node['task'] for node in started['definition']['nodes'] if node['id'] == 'remote-file')
                status, accepted = post(server, '/agent/submit', {name: request[name]
                    for name in ('spec', 'idempotency_key')}, token=owner_token)
                assert status == 200, accepted
                source = accepted['task_id']
                with authorization_scope(owner):
                    runtime.pause(source)
                child = recover_nodes(runtime, source, {'actor': reviewer})
                with runtime.store.connection() as connection:
                    assert connection.execute('SELECT count(*) FROM agent_dag_batches').fetchone()[0] == 0
                    assert connection.execute('SELECT count(*) FROM agent_dag_local_tasks').fetchone()[0] == 0
                yield SimpleNamespace(runtime=runtime, coordinator=coordinator, server=server, source=source,
                    child=child, users=users, owner=owner, reviewer=reviewer, owner_token=owner_token,
                    reviewer_token=reviewer_token, output=output, body=body)
            finally:
                coordinator.close()


def grant(value):
    reviewed = evidence_review(value.server, value.source, value.child,
                               token=value.reviewer_token, recipient_policy='source_owner')
    status, result = evidence_create(value.server, reviewed, token=value.reviewer_token)
    assert status == 200, result
    return result['evidence']['grant_id']


def test_registered_http_peer_resolves_other_owner_completion_without_general_task_access(tmp_path, monkeypatch):
    with remote_recovery(tmp_path, monkeypatch) as value:
        identifier = grant(value)
        with authorization_scope(value.owner), pytest.raises(AgentTaskError, match='another caller'):
            value.runtime.get(value.child)
        binding = actual_binding(value.runtime, value.source)
        host_binding = value.coordinator.batches.transfer_binding('source')
        proof = resolve_remote_evidence(value.coordinator.transfers.remote, 'source', host_binding, identifier, binding)
        assert proof['task_id'] == value.child and proof['node']['node_id'] == 'remote-file'
        assert value.runtime.store.get(value.child)['owner']['user_id'] == 'reviewer'
        assert value.output.read_bytes() == value.body
        status, denied = post(value.server, '/agent/transfer/peer', {'operation': 'evidence', 'request': {
            'grant_id': identifier, 'binding': binding}}, token=value.reviewer_token)
        assert status == 409, denied
        value.users.set_role('reviewer', 'viewer')
        with pytest.raises(AgentTaskError):
            resolve_remote_evidence(value.coordinator.transfers.remote, 'source', host_binding, identifier, binding)


@pytest.mark.parametrize('change', ['request_key_hash', 'submitted_spec_digest', 'batch_id', 'graph_hash', 'node_id'])
def test_fresh_remote_resolution_refuses_a_different_original_coordinator_witness(tmp_path, monkeypatch, change):
    with remote_recovery(tmp_path, monkeypatch) as value:
        identifier = grant(value)
        binding = actual_binding(value.runtime, value.source)
        binding[change] = 'different-node' if change == 'node_id' else ('f' * (32 if change == 'batch_id' else 64))
        with pytest.raises(AgentTaskError):
            resolve_remote_evidence(value.coordinator.transfers.remote, 'source',
                value.coordinator.batches.transfer_binding('source'), identifier, binding)


@pytest.mark.parametrize('boundary', ['reserve', 'consume_review'])
def test_issuer_revocation_inside_creation_rolls_back_portable_consent(tmp_path, monkeypatch, boundary):
    with remote_recovery(tmp_path, monkeypatch) as value:
        reviewed = evidence_review(value.server, value.source, value.child, token=value.reviewer_token)
        records = value.runtime.transfers.source.records
        original = getattr(records, boundary)
        def revoke(connection, *args):
            result = original(connection, *args)
            value.users.set_role('reviewer', 'viewer')
            return result
        monkeypatch.setattr(records, boundary, revoke)
        status, denied = evidence_create(value.server, reviewed, token=value.reviewer_token)
        assert status == 409, denied
        with value.runtime.store.connection() as connection:
            count = connection.execute("SELECT count(*) FROM agent_transfer_grants WHERE kind='evidence'")
            assert count.fetchone()[0] == 0
            count = connection.execute("SELECT count(*) FROM agent_transfer_intents WHERE kind='evidence'")
            assert count.fetchone()[0] == 0


def test_keyed_standalone_recovery_resolves_without_a_fabricated_dag_admission(tmp_path, monkeypatch):
    with remote_recovery(tmp_path, monkeypatch) as value:
        spec = value.runtime.store.get(value.source)['spec']
        spec['options'].pop('dag_batch')
        status, accepted = post(value.server, '/agent/submit', {'spec': spec,
            'idempotency_key': 'actual-standalone-portable-source'}, token=value.owner_token)
        assert status == 200, accepted
        source = accepted['task_id']
        with authorization_scope(value.owner):
            value.runtime.pause(source)
        child = recover_nodes(value.runtime, source, {'actor': value.reviewer})
        reviewed = evidence_review(value.server, source, child, token=value.reviewer_token,
                                   recipient_policy='source_owner')
        status, created = evidence_create(value.server, reviewed, token=value.reviewer_token)
        assert status == 200, created
        binding = actual_binding(value.runtime, source)
        proof = resolve_remote_evidence(value.coordinator.transfers.remote, 'source',
            value.coordinator.batches.transfer_binding('source'), created['evidence']['grant_id'], binding)
        assert proof['source_task'] == source and proof['task_id'] == child and 'node' not in proof
        with value.runtime.store.connection() as connection:
            assert connection.execute('SELECT count(*) FROM agent_dag_local_tasks').fetchone()[0] == 0
            submitted = connection.execute('SELECT 1 FROM agent_task_submissions WHERE task_id=?', (source,))
            assert submitted.fetchone() is None


def test_revoked_wire_consent_never_recreates_wire_authority(tmp_path, monkeypatch):
    with remote_recovery(tmp_path, monkeypatch) as value:
        reviewed = evidence_review(value.server, value.source, value.child, token=value.reviewer_token,
                                   recipient_policy='source_owner')
        status, created = evidence_create(value.server, reviewed, token=value.reviewer_token)
        assert status == 200, created
        identifier = created['evidence']['grant_id']
        status, revoked = post(value.server, '/agent/transfer', {'operation': 'revoke_evidence',
            'request': {'grant_id': identifier}}, token=value.owner_token)
        assert status == 200 and revoked['evidence']['state'] == 'revoked'
        status, denied = evidence_create(value.server, reviewed, token=value.reviewer_token)
        assert status == 409, denied
        with pytest.raises(AgentTaskError):
            resolve_remote_evidence(value.coordinator.transfers.remote, 'source',
                value.coordinator.batches.transfer_binding('source'), identifier,
                actual_binding(value.runtime, value.source))
        with value.runtime.store.connection() as connection:
            record = value.runtime.transfers.source.records.find(connection, identifier)
            assert record['state'] == 'revoked' and record['held'] is False
