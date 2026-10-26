"""Live portable grants revalidate real recovery provenance without granting task reads or input."""
from contextlib import contextmanager
from hashlib import sha256
import json

import pytest

from headless.test_agent_transfer_source_lineage import recovered_file_node, damage_lineage
from headless.test_agent_transfer_peer_security import post
from je_auto_control.utils.agent_runtime.submission import submitted_digest
from je_auto_control.utils.rest_api.rest_server import RestApiServer


@contextmanager
def evidence_server(runtime, users=None):
    server = RestApiServer(port=0, token='owned-evidence-account', user_store=users,
                           agent_runtime=runtime, enable_audit=False, use_environment_users=False)
    server.start()
    try:
        yield server
    finally:
        server.stop()


def evidence_review(server, source, child, *, token=None, recipient_policy='caller'):
    status, reply = post(server, '/agent/transfer', {'operation': 'review_evidence', 'request': {
        'source_task': source, 'task_id': child, 'recipient_policy': recipient_policy,
        'idempotency_key': 'actual-portable-evidence'}}, token=token)
    assert status == 200, reply
    assert reply['approval_required'] is True
    return reply


def evidence_create(server, reviewed, *, token=None):
    status, reply = post(server, '/agent/transfer', {'operation': 'create_evidence', 'request': {
        'review': reviewed['review'], 'note': 'Approve only this real completion evidence',
        'idempotency_key': 'actual-portable-evidence'}}, token=token)
    return status, reply


def actual_binding(runtime, source):
    with runtime.store.connection() as connection:
        request = connection.execute('SELECT key_hash FROM agent_request_keys WHERE task_id=?', (source,)).fetchone()
        row = runtime.store.read_task(connection, source)
    result = {'source_task': source, 'request_key_hash': request['key_hash'],
              'submitted_spec_digest': submitted_digest(row['spec'])}
    tag = row['spec']['options'].get('dag_batch')
    if tag is not None:
        result.update({name: tag[name] for name in ('batch_id', 'graph_hash', 'node_id')})
    return result


def evidence_read(server, grant, binding, *, token=None):
    return post(server, '/agent/transfer/peer', {'operation': 'evidence', 'request': {
        'grant_id': grant, 'binding': binding}}, token=token)


def test_actual_local_dag_recovery_resolves_only_the_reviewed_portable_proof(tmp_path):
    with recovered_file_node(tmp_path) as (runtime, source, child, output, body, _batch):
        before = runtime.store.actions(child)
        with evidence_server(runtime) as server:
            reviewed = evidence_review(server, source, child)
            status, created = evidence_create(server, reviewed)
            assert status == 200, created
            grant = created['evidence']['grant_id']
            binding = actual_binding(runtime, source)
            status, proof = evidence_read(server, grant, binding)
            assert status == 200, proof
            assert proof['source_task'] == source and proof['task_id'] == child
            assert proof['grant_id'] == grant and proof['evidence_only'] is True and proof['input_authorized'] is False
            assert proof['submitted_spec_digest'] == binding['submitted_spec_digest']
            expected = {'key_hash': binding['request_key_hash'],
                        'submitted_spec_digest': binding['submitted_spec_digest']}
            digest = sha256(json.dumps(expected, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            assert proof['node']['request_digest'] == digest
            assert len(proof['chain']) == 1 and proof['chain'][0]['source_task'] == source
            assert str(tmp_path) not in json.dumps(proof)
            assert runtime.store.actions(child) == before and output.read_bytes() == body
            status, again = evidence_create(server, reviewed)
            assert status == 200 and again == created


@pytest.mark.parametrize('boundary', ['create', 'resolve'])
def test_portable_evidence_cannot_bypass_a_real_local_admission_by_stripping_its_tag(tmp_path, boundary):
    with recovered_file_node(tmp_path) as (runtime, source, child, _output, _body, _batch):
        with evidence_server(runtime) as server:
            reviewed = evidence_review(server, source, child)
            binding = actual_binding(runtime, source)
            created = evidence_create(server, reviewed)[1] if boundary == 'resolve' else None
            with runtime.store.connection(write=True) as connection:
                damage_lineage(connection, runtime, source, child, 'stripped_tag')
            status, denied = (evidence_create(server, reviewed) if boundary == 'create' else
                             evidence_read(server, created['evidence']['grant_id'], binding))
            assert status == 409, denied
            if boundary == 'create':
                with runtime.store.connection() as connection:
                    count = connection.execute("SELECT count(*) FROM agent_transfer_grants WHERE kind='evidence'")
                    assert count.fetchone()[0] == 0


def test_existing_local_handoff_grant_does_not_select_the_new_wire_family(tmp_path):
    with recovered_file_node(tmp_path) as (runtime, source, child, _output, _body, batch):
        request = {'batch_id': batch, 'node_id': 'file-node', 'task_id': child}
        reviewed = runtime.recovery.control('review_handoff', request)
        old = runtime.recovery.control('create_handoff', {**request, 'review': reviewed['handoff_review'],
                                                         'note': 'Approve only the original local grant'})
        with evidence_server(runtime) as server:
            status, denied = evidence_read(server, old['handoff']['id'], actual_binding(runtime, source))
            assert status == 409, denied
        candidate, _chain = runtime.recovery.handoff_evidence(batch, 'file-node', source, child, old['handoff']['id'])
        assert candidate['task_id'] == child
