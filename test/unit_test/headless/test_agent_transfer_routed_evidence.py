"""Real named source/coordinator services route consent without forwarding a local identity or authority."""
from copy import deepcopy
import json

import pytest

from headless.test_agent_transfer_evidence_remote import remote_recovery
from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime import AgentTaskError, transport
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@pytest.fixture
def routed(tmp_path, monkeypatch):
    with remote_recovery(tmp_path, monkeypatch) as value:
        users = UserStore(tmp_path / 'actual-coordinator-users.json')
        users.add_user(user_id='coordinator', display_name='Coordinator', role='admin')
        users.add_user(user_id='other', display_name='Other coordinator', role='admin')
        actor = AuthorizationContext('coordinator', 'admin', store_path=str(users.path))
        book = admin_client._default_console
        book.add_host('source', value.server.base_url, value.reviewer_token)
        wire, invoke = [], transport.request_json
        def observe(url, **kwargs):
            if url == value.server.base_url + '/agent/transfer':
                assert kwargs['token'] == value.reviewer_token and kwargs.get('delegate_local') is False
                record = deepcopy(kwargs['body'])
                wire.append(record)
                result = invoke(url, **kwargs)
                record['reply'] = deepcopy(result)
                return result
            return invoke(url, **kwargs)
        monkeypatch.setattr(transport, 'request_json', observe)
        value.actor, value.coordinator_users, value.book, value.wire = actor, users, book, wire
        original = value.coordinator
        try:
            with authorization_scope(actor):
                yield value
        finally:
            if value.coordinator is not original:
                value.coordinator.close()


def review(value):
    return value.coordinator.transfers.control('review_evidence', {'host': 'source',
        'source_task': value.source, 'task_id': value.child, 'recipient_policy': 'source_owner',
        'idempotency_key': 'actual-routed-evidence'})


def approval(reviewed):
    return {'host': 'source', 'review': reviewed['review'], 'note': 'Approve only real completion proof',
            'idempotency_key': 'actual-routed-evidence'}


def count_grants(value):
    with value.runtime.store.connection() as database:
        return database.execute("SELECT count(*) FROM agent_transfer_grants WHERE kind='evidence'").fetchone()[0]


def test_named_coordinator_reviews_creates_lists_and_revokes_one_actual_source_evidence_grant(routed):
    value = routed
    control = value.coordinator.transfers.control
    reviewed = review(value)
    assert reviewed['review'] != value.wire[-1]['reply']['review']
    assert reviewed['evidence']['task_id'] == value.child and count_grants(value) == 0
    request = approval(reviewed)
    created = control('create_evidence', request)['evidence']
    assert created['summary'] == reviewed['evidence'] and created['state'] == 'active'
    assert control('create_evidence', request)['evidence'] == created
    assert control('get_evidence', {'host': 'source', 'grant_id': created['grant_id']})['evidence'] == created
    listed = control('list_evidence', {'host': 'source', 'source_task': value.source})['evidence']
    assert listed == [created]
    revoked = control('revoke_evidence', {'host': 'source', 'grant_id': created['grant_id']})['evidence']
    assert revoked['state'] == 'revoked' and revoked['summary'] == created['summary']
    with pytest.raises(AgentTaskError):
        control('create_evidence', request)
    assert count_grants(value) == 1 and value.coordinator.list() == []
    with authorization_scope(value.owner), pytest.raises(AgentTaskError, match='another caller'):
        value.runtime.get(value.child)
    encoded = json.dumps(value.wire)
    assert str(value.coordinator_users.path) not in encoded and value.owner_token not in encoded
    assert all('host' not in item['request'] and 'owner' not in item['request'] for item in value.wire)
    assert value.output.read_bytes() == value.body


@pytest.mark.parametrize('fault', ['lost-reply', 'changed-summary', 'restart-after-lost-reply'])
def test_ambiguous_creation_recovers_one_exact_durable_evidence_consent(routed, monkeypatch, fault):
    from je_auto_control.utils.agent_runtime import AgentRuntime
    value = routed
    reviewed = review(value)
    request = approval(reviewed)
    original = transport.request_json
    dropped = []
    def ambiguous(url, **kwargs):
        result = original(url, **kwargs)
        if (url == value.server.base_url + '/agent/transfer'
                and kwargs['body']['operation'] == 'create_evidence' and not dropped):
            dropped.append(True)
            if fault == 'changed-summary':
                result['evidence']['summary']['verification'][0]['kind'] = 'changed-finite-criterion'
            else:
                raise OSError('Owned source committed; acknowledgement intentionally lost')
        return result
    monkeypatch.setattr(transport, 'request_json', ambiguous)
    with pytest.raises(AgentTaskError):
        value.coordinator.transfers.control('create_evidence', request)
    assert count_grants(value) == 1
    if fault == 'restart-after-lost-reply':
        path = value.coordinator.store.path
        value.coordinator.close()
        value.coordinator = AgentRuntime(path, targets={})
    current = value.coordinator.transfers.control('create_evidence', request)['evidence']
    assert current['summary'] == reviewed['evidence'] and current['state'] == 'active'
    assert count_grants(value) == 1 and len(dropped) == 1
    with value.coordinator.store.connection() as database:
        records = value.coordinator.transfers.source.records
        routes = records.entries(database, 'route')
    assert len(routes) == 1 and routes[0]['scope']['evidence'] == reviewed['evidence']
    assert 'manifest' not in routes[0]['scope'] and routes[0]['account'] is None


@pytest.mark.parametrize('change', ['host', 'actor', 'key', 'issuer-role'])
def test_changed_host_identity_key_or_source_role_cannot_mint_a_routed_grant(routed, change):
    value = routed
    reviewed = review(value)
    request = approval(reviewed)
    if change == 'host':
        value.book.add_host('source', value.server.base_url, value.owner_token)
    elif change == 'key':
        request['idempotency_key'] = 'another-key'
    elif change == 'issuer-role':
        value.users.set_role('reviewer', 'viewer')
    actor = (AuthorizationContext('other', 'admin', store_path=str(value.coordinator_users.path))
             if change == 'actor' else value.actor)
    with authorization_scope(actor), pytest.raises(AgentTaskError):
        value.coordinator.transfers.control('create_evidence', request)
    assert count_grants(value) == 0 and value.output.read_bytes() == value.body
