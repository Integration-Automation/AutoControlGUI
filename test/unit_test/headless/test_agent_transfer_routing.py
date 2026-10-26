"""Actual independent source/coordinator runtimes bind routed consent before authenticated creation."""
import base64
from concurrent.futures import CancelledError
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from headless.test_agent_transfer_source import completed_source
from headless.test_agent_transfer_peer_security import post
from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, transport
from je_auto_control.utils.agent_runtime.dag_batches import DagBatches
from je_auto_control.utils.agent_runtime import transfer_routing
from je_auto_control.utils.exception.cancellation import CancellationToken, cancellation_scope
from je_auto_control.utils.rest_api.rest_server import RestApiServer
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@pytest.fixture
def routed(tmp_path, monkeypatch):
    source_root = tmp_path / 'source'
    source_root.mkdir()
    with completed_source(source_root, named=True) as (source, task, _output, body, source_users):
        server = RestApiServer(port=0, token='owned-source-service', user_store=source_users,
                               agent_runtime=source, enable_audit=False, use_environment_users=False)
        users = UserStore(tmp_path / 'coordinator-users.json')
        users.add_user(user_id='coordinator', display_name='Coordinator', role='admin')
        actor = AuthorizationContext('coordinator', 'admin', store_path=str(users.path))
        runtime = AgentRuntime(tmp_path / 'coordinator.sqlite3', targets={})
        server.start()
        book = admin_client.AdminConsoleClient(persist_path=tmp_path / 'hosts.json')
        book.add_host('source', server.base_url, source_users.rotate_token('owner'))
        monkeypatch.setattr(admin_client, '_default_console', book)
        wire = []
        original = transport.request_json

        def observe(url, **kwargs):
            envelope = kwargs.get('body')
            if isinstance(envelope, dict) and url.endswith('/agent/transfer'):
                assert kwargs.get('delegate_local') is False
                record = deepcopy(envelope)
                wire.append(record)
                reply = original(url, **kwargs)
                record['reply'] = deepcopy(reply)
                return reply
            return original(url, **kwargs)

        monkeypatch.setattr(transport, 'request_json', observe)
        value = SimpleNamespace(runtime=runtime, source=source, server=server, task=task, body=body,
                                source_users=source_users, users=users, actor=actor, book=book, wire=wire)
        try:
            with authorization_scope(actor):
                yield value
        finally:
            value.runtime.close()
            server.stop()


def review(routed, **changes):
    request = {'host': 'source', 'source_task': routed.task, 'selection': [{'criterion': 0, 'names': []}],
               'recipient_policy': 'caller', 'idempotency_key': 'routed-exact-export'}
    return routed.runtime.transfers.control('review_export', {**request, **changes})


def create(routed, reviewed, **changes):
    request = {'host': 'source', 'review': reviewed['review'], 'note': 'Approve these exact remote bytes',
               'idempotency_key': 'routed-exact-export'}
    return routed.runtime.transfers.control('create_export', {**request, **changes})


def test_real_routed_consent_returns_a_local_token_and_exact_source_bytes(routed):
    reviewed = review(routed)
    peer_review = routed.wire[-1]['reply']['review']
    assert reviewed['review'] != peer_review and reviewed['approval_required'] is True
    assert reviewed['digest'] == routed.wire[-1]['reply']['digest']
    assert 'host' not in routed.wire[-1]['request']
    created = create(routed, reviewed)['export']
    assert created['manifest'] == reviewed['manifest'] and created['state'] == 'active'
    assert routed.wire[-1]['request']['review'] == peer_review
    pin = routed.runtime.batches.transfer_binding('source')
    digest = created['manifest']['files'][0]['chunks'][0]
    chunk = routed.runtime.transfers.remote.call('source', pin, 'chunk',
        {'export_id': created['export_id'], 'sha256': digest}, 3)
    assert base64.b64decode(chunk['data']) == routed.body
    assert routed.runtime.list() == []
    with pytest.raises(AgentTaskError):
        routed.runtime.get(routed.task)
    encoded = json.dumps(reviewed)
    assert str(routed.users.path) not in encoded and routed.actor.user_id not in encoded
    with routed.source.store.connection() as connection:
        scope = json.loads(connection.execute('SELECT payload FROM agent_transfer_grants').fetchone()[0])['scope']
    assert scope['issuer']['user_id'] == scope['recipient']['user_id'] == 'owner'
    assert scope['issuer']['store_path'] == str(routed.source_users.path)


def test_routed_management_get_list_and_revoke_use_the_actual_source(routed):
    created = create(routed, review(routed))['export']
    controller = routed.runtime.transfers
    assert controller.control('get_export', {'host': 'source', 'export_id': created['export_id']})['export'] == created
    assert controller.control('list_exports', {'host': 'source', 'source_task': routed.task})['exports'] == [created]
    revoked = controller.control('revoke_export', {'host': 'source', 'export_id': created['export_id']})['export']
    assert revoked['state'] == 'revoked' and revoked['cleanup_pending'] is False
    assert routed.runtime.list() == []


def test_approved_intent_precedes_wire_and_lost_ack_recovers_after_coordinator_restart(routed, monkeypatch):
    reviewed = review(routed)
    original = transport.request_json
    sent = []

    def lose_ack(url, **kwargs):
        envelope = kwargs.get('body', {})
        if envelope.get('operation') == 'create_export':
            with routed.runtime.store.connection() as connection:
                rows = connection.execute('SELECT state,note_hash FROM agent_transfer_routed_reviews').fetchall()
                assert len(rows) == 1 and rows[0]['state'] == 'active' and rows[0]['note_hash']
            sent.append(deepcopy(envelope))
            reply = original(url, **kwargs)
            if len(sent) == 1:
                raise OSError('owned response lost after actual source commit')
            return reply
        return original(url, **kwargs)

    monkeypatch.setattr(transport, 'request_json', lose_ack)
    with pytest.raises(AgentTaskError):
        create(routed, reviewed)
    with routed.source.store.connection() as connection:
        identifier = connection.execute('SELECT id FROM agent_transfer_grants').fetchone()[0]
    path = routed.runtime.store.path
    routed.runtime.close()
    routed.runtime = AgentRuntime(path, targets={})
    created = create(routed, reviewed)['export']
    assert created['export_id'] == identifier and sent[0] == sent[1]
    with routed.source.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0] == 1


def test_routed_recipient_policy_derives_only_the_sources_actual_identities(routed):
    routed.book.add_host('source', routed.server.base_url, routed.source_users.rotate_token('reviewer'))
    created = create(routed, review(routed, recipient_policy='source_owner'))['export']
    with routed.source.store.connection() as connection:
        scope = json.loads(connection.execute('SELECT payload FROM agent_transfer_grants').fetchone()[0])['scope']
    assert scope['issuer']['user_id'] == 'reviewer' and scope['recipient']['user_id'] == 'owner'
    pin = routed.runtime.batches.transfer_binding('source')
    with pytest.raises(AgentTaskError):
        routed.runtime.transfers.remote.call('source', pin, 'export', {'export_id': created['export_id']}, 3)


def test_explicit_local_host_uses_only_the_original_local_source(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        def forbidden(*_args, **_kwargs):
            raise AssertionError('explicit local selection opened the remote host book')
        monkeypatch.setattr(DagBatches, 'transfer_binding', forbidden)
        reviewed = runtime.transfers.control('review_export', {'host': 'local', 'source_task': task,
            'selection': [{'criterion': 0, 'names': []}], 'recipient_policy': 'caller', 'idempotency_key': 'local'})
        exported = runtime.transfers.control('create_export', {'host': 'local', 'review': reviewed['review'],
            'note': 'Approve only local outcomes', 'idempotency_key': 'local'})['export']
        assert runtime.transfers.peer('export', {'export_id': exported['export_id']}) == reviewed['manifest']


@pytest.mark.parametrize('change', ['caller', 'host', 'token', 'key'])
def test_routed_review_cannot_be_rebound_before_creation(routed, monkeypatch, change):
    reviewed = review(routed)
    changes = {}
    if change == 'caller':
        routed.users.add_user(user_id='other-admin', display_name='Other', role='admin')
        actor = AuthorizationContext('other-admin', 'admin', store_path=str(routed.users.path))
    else:
        actor = routed.actor
    if change == 'host':
        source = routed.book.list_hosts()[0]
        routed.book.add_host('alias', source.base_url, source.token)
        changes['host'] = 'alias'
    if change == 'token':
        routed.book.add_host('source', routed.server.base_url, 'replacement-owned-token')
    if change == 'key':
        changes['idempotency_key'] = 'changed-key'

    def forbidden(*_args, **_kwargs):
        raise AssertionError('changed review authority reached the network')

    monkeypatch.setattr(transport, 'request_json', forbidden)
    with authorization_scope(actor), pytest.raises(AgentTaskError):
        create(routed, reviewed, **changes)


def test_a_foreign_peer_review_is_not_a_coordinator_review(routed, monkeypatch):
    token = routed.book.list_hosts()[0].token
    status, foreign = post(routed.server, '/agent/transfer', {'operation': 'review_export', 'request': {
        'source_task': routed.task, 'selection': [{'criterion': 0, 'names': []}],
        'recipient_policy': 'caller', 'idempotency_key': 'routed-exact-export'}}, token=token)
    assert status == 200

    def forbidden(*_args, **_kwargs):
        raise AssertionError('an unbound foreign review reached the network')

    monkeypatch.setattr(transport, 'request_json', forbidden)
    with pytest.raises(AgentTaskError):
        create(routed, foreign)


@pytest.mark.parametrize('change', [{'note': 'changed approval'}, {'idempotency_key': 'changed-key'}])
def test_committed_routed_consent_requires_the_original_note_and_key(routed, monkeypatch, change):
    reviewed = review(routed)
    create(routed, reviewed)

    def forbidden(*_args, **_kwargs):
        raise AssertionError('a changed consumed consent reached the network')

    monkeypatch.setattr(transport, 'request_json', forbidden)
    with pytest.raises(AgentTaskError):
        create(routed, reviewed, **change)


def test_same_routed_consent_remains_an_exact_retry_after_review_ttl(routed, monkeypatch):
    reviewed = review(routed)
    first = create(routed, reviewed)
    actual_time = transfer_routing.time.time()
    monkeypatch.setattr(transfer_routing.time, 'time', lambda: actual_time + 301)
    assert create(routed, reviewed) == first
    with routed.source.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0] == 1


def test_unapproved_routed_review_expires_without_forwarding_creation(routed, monkeypatch):
    reviewed = review(routed)
    actual_time = transfer_routing.time.time()
    monkeypatch.setattr(transfer_routing.time, 'time', lambda: actual_time + 301)

    def forbidden(*_args, **_kwargs):
        raise AssertionError('expired unapproved route reached the source')

    monkeypatch.setattr(transport, 'request_json', forbidden)
    with pytest.raises(AgentTaskError):
        create(routed, reviewed)


def test_local_authority_loss_after_intent_sql_rolls_back_before_wire(routed, monkeypatch):
    reviewed = review(routed)
    records = routed.runtime.transfers.source.records
    original = records.consume_review

    def revoked(*args, **kwargs):
        result = original(*args, **kwargs)
        routed.users.set_role('coordinator', 'operator')
        return result

    def forbidden(*_args, **_kwargs):
        raise AssertionError('authority lost inside local intent transaction reached the source')

    monkeypatch.setattr(records, 'consume_review', revoked)
    monkeypatch.setattr(transport, 'request_json', forbidden)
    with pytest.raises(AgentTaskError):
        create(routed, reviewed)
    with routed.runtime.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_transfer_routed_reviews').fetchone()[0] == 0


def test_cancellation_after_durable_intent_preserves_an_exact_future_retry(routed, monkeypatch):
    reviewed = review(routed)
    router = routed.runtime.transfers._routing
    original = router._approved
    token = CancellationToken('routed-consent')

    def cancelled(*args, **kwargs):
        record = original(*args, **kwargs)
        token.cancel()
        return record

    monkeypatch.setattr(router, '_approved', cancelled)
    with cancellation_scope(token), pytest.raises(CancelledError):
        create(routed, reviewed)
    with routed.runtime.store.connection() as connection:
        assert connection.execute('SELECT state FROM agent_transfer_routed_reviews').fetchone()[0] == 'active'
    with routed.source.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0] == 0
    monkeypatch.setattr(router, '_approved', original)
    assert create(routed, reviewed)['export']['state'] == 'active'


def test_a_different_valid_manifest_in_the_actual_ack_is_not_the_approved_outcome(routed, monkeypatch):
    reviewed = review(routed)
    original = transport.request_json

    def changed(url, **kwargs):
        reply = original(url, **kwargs)
        if kwargs.get('body', {}).get('operation') == 'create_export':
            reply = deepcopy(reply)
            reply['export']['export_id'] = 'f' * 32
            reply['export']['manifest']['export_id'] = 'f' * 32
        return reply

    monkeypatch.setattr(transport, 'request_json', changed)
    with pytest.raises(AgentTaskError, match='manifest'):
        create(routed, reviewed)
    monkeypatch.setattr(transport, 'request_json', original)
    assert create(routed, reviewed)['export']['manifest'] == reviewed['manifest']
    with routed.source.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0] == 1


def test_coordinator_admin_cannot_borrow_source_admin_authority(routed):
    actor = AuthorizationContext('other', 'operator', store_path=str(routed.source_users.path))
    with authorization_scope(actor):
        other = routed.source.submit(routed.source.store.get(routed.task)['spec'])
        assert routed.source.finish(other.task_id).state == 'succeeded'
    with pytest.raises(AgentTaskError):
        review(routed, source_task=other.task_id)
    assert routed.runtime.transfers._routing._reviews == {}
    with routed.source.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0] == 0


def test_network_budget_uses_the_remaining_whole_operation_deadline(routed, monkeypatch):
    controller = routed.runtime.transfers
    original_prepare = controller._routing._prepare
    original_request = transport.request_json
    observed = []

    def elapsed(*args, **kwargs):
        original_prepare(*args, **kwargs)
        controller._life.deadline -= 5

    def limited(url, **kwargs):
        observed.append(kwargs['timeout'])
        assert 0 < kwargs['timeout'] < 25
        return original_request(url, **kwargs)

    monkeypatch.setattr(controller._routing, '_prepare', elapsed)
    monkeypatch.setattr(transport, 'request_json', limited)
    assert review(routed)['approval_required'] is True and len(observed) == 1


def test_pending_route_cap_refuses_more_source_requests(routed, monkeypatch):
    reviewed = review(routed)
    router = routed.runtime.transfers._routing
    pending = router._reviews[reviewed['review']]
    router._reviews = {f'{number:032x}': {**deepcopy(pending), 'review': f'{number:032x}'} for number in range(128)}

    def forbidden(*_args, **_kwargs):
        raise AssertionError('a full private pending-review table reached the source')

    monkeypatch.setattr(transport, 'request_json', forbidden)
    with pytest.raises(AgentTaskError, match='quota'):
        review(routed)


def test_closing_the_runtime_discards_unapproved_private_routed_reviews(routed):
    review(routed)
    router = routed.runtime.transfers._routing
    assert len(router._reviews) == 1
    routed.runtime.close()
    assert router._reviews == {}
    with routed.source.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0] == 0
