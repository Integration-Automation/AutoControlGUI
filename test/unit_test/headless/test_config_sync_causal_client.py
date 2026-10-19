"""Controlled causal HTTP delivery preserves exact retries, bounded rebasing and durable snapshot receipts."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event

import pytest

import je_auto_control as ac
from headless.test_config_sync_causal_store import actor, register


def connected(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    from je_auto_control.utils.http_client import http_client
    path = tmp_path / 'server.sqlite3'
    server = ac.CausalConfigStore(path)
    register(server, 'desktop')
    web = TestClient(create_app(config_store_path=path, shared_secret='synthetic-only', serve_web_viewer=False))
    calls = []
    def perform(call):
        calls.append(dict(call))
        assert call['follow_redirects'] is False
        response = web.request(call['method'], call['url'], content=call['body'], headers=call['headers'])
        return {'status': response.status_code, 'text': response.text}
    monkeypatch.setattr(http_client, 'perform_call', perform)
    queue = ac.SyncOutbox(tmp_path / 'outbox.sqlite3')
    queue.identity('https://controlled.invalid', 'alice', origin='desktop')
    client = ac.CausalSyncClient('https://controlled.invalid', user_id='alice', secret='synthetic-only')
    entry = ac.SyncEntry('settings', 'theme', {'value': 'dark'}, {'desktop': 1}, 'edit', 'desktop')
    operation = ac.SyncOperation('edit', 'https://controlled.invalid', 'alice', 'desktop', (entry,))
    queue.enqueue(operation)
    return client, queue, operation, server, calls, perform


def test_causal_client_flush_confirms_snapshot_atomically_with_delivery(tmp_path, monkeypatch):
    client, queue, operation, server, calls, _perform = connected(tmp_path, monkeypatch)
    report = client.flush(queue)
    assert report.delivered == 1 and report.pending == 0
    assert [call['method'] for call in calls] == ['GET', 'PUT']
    assert all(call['url'].endswith('/config/alice/causal') for call in calls)
    assert queue.snapshot(endpoint=operation.endpoint, user_id='alice') == server.get('alice')
    assert queue.snapshot(endpoint=operation.endpoint, user_id='bob') is None
    assert b'synthetic-only' not in (tmp_path / 'outbox.sqlite3').read_bytes()


def test_uncertain_accepted_result_retries_identical_prepared_request_before_fetch(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    client, queue, operation, server, calls, perform = connected(tmp_path, monkeypatch)
    first = [True]
    def uncertain(call):
        reply = perform(call)
        if call['method'] == 'PUT' and first[0]:
            first[0] = False
            raise OSError('controlled connection loss after commit')
        return reply
    monkeypatch.setattr(http_client, 'perform_call', uncertain)
    policy = ac.SyncRetryPolicy(max_attempts=1, backoff=0)
    report = client.flush(queue, policy=policy)
    assert report.delivered == 0 and report.pending == 1
    prepared = queue.pending(endpoint=operation.endpoint, user_id='alice')[0].prepared
    accepted_revision = server.get('alice').revision
    register(server, 'laptop')
    calls.clear()
    reopened = ac.SyncOutbox(tmp_path / 'outbox.sqlite3')
    report = client.flush(reopened, policy=policy)
    assert report.delivered == 1 and report.pending == 0
    assert [call['method'] for call in calls] == ['PUT']
    request = json.loads(calls[0]['body'])
    assert request['bucket'] == prepared['bucket'] and request['base_revision'] == prepared['base_revision']
    assert reopened.status(endpoint=operation.endpoint, user_id='alice')['confirmed_revision'] == accepted_revision
    assert reopened.snapshot(endpoint=operation.endpoint, user_id='alice').revision == accepted_revision + 1


def test_definite_stale_cas_rebases_without_changing_logical_delivery_identity(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    client, queue, operation, server, calls, perform = connected(tmp_path, monkeypatch)
    first = [True]
    def competing(call):
        if call['method'] == 'PUT' and first[0]:
            first[0] = False
            register(server, 'laptop')
        return perform(call)
    monkeypatch.setattr(http_client, 'perform_call', competing)
    report = client.flush(queue, max_rebases=2)
    assert report.delivered == 1
    requests = [json.loads(call['body']) for call in calls if call['method'] == 'PUT']
    assert len(requests) == 2 and requests[0]['operation_id'] == requests[1]['operation_id'] == operation.delivery_id
    assert requests[0]['base_revision'] + 1 == requests[1]['base_revision']


def test_operation_id_conflict_keeps_frozen_request_and_never_rebases(tmp_path, monkeypatch):
    client, queue, operation, server, calls, perform = connected(tmp_path, monkeypatch)
    current = server.get('alice')
    other = operation.entries[0].evolve({'value': 'other'}, origin='desktop', operation_id='other')
    server.commit('alice', current.with_entries((other,)), base_revision=current.revision,
                  operation_id=operation.delivery_id, actor=actor('desktop'))
    client.flush(queue, max_rebases=2)
    assert [call['method'] for call in calls] == ['GET', 'PUT']
    state = queue.status(endpoint=operation.endpoint, user_id='alice')
    assert state['conflict'] == 1 and state['pending'] == 1
    assert queue.pending(endpoint=operation.endpoint, user_id='alice')[0].prepared is not None
    assert queue.snapshot(endpoint=operation.endpoint, user_id='alice') is None
    assert server.get('alice').live_entries == (other,)


def test_obsolete_peer_is_blocked_without_a_write_and_cancellation_keeps_pending(tmp_path, monkeypatch):
    client, queue, operation, server, calls, _perform = connected(tmp_path, monkeypatch)
    state = server.get('alice')
    peers = state.peers
    peers.retire('desktop')
    server.commit('alice', state.with_peers(peers), base_revision=state.revision,
                  operation_id='retire', actor=actor('desktop', 'retire', peer_id='desktop'))
    assert client.flush(queue, cancelled=lambda: True).cancelled is True
    assert calls == []
    result = client.flush(queue)
    assert result.pending == 1 and [call['method'] for call in calls] == ['GET']
    assert queue.status(endpoint=operation.endpoint, user_id='alice')['blocked'] == 1


def test_old_server_is_refused_without_any_mutation(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    mutations = []
    def old_server(call):
        if call['method'] == 'PUT':
            mutations.append(call)
        return {'status': 404, 'text': 'missing'}
    monkeypatch.setattr(http_client, 'perform_call', old_server)
    client = ac.CausalSyncClient('https://old.invalid', user_id='alice')
    with pytest.raises(ac.ConfigSyncError):
        client.fetch()
    assert mutations == []


def test_snapshot_receipt_rejects_uncommitted_or_mismatched_evidence(tmp_path, monkeypatch):
    _client, queue, operation, server, _calls, _perform = connected(tmp_path, monkeypatch)
    with pytest.raises(ac.ConfigSyncError):
        ac.CausalReceipt(99, server.get('alice'))
    receipt = ac.CausalReceipt(server.get('alice').revision, server.get('alice'))
    with pytest.raises(ac.ConfigSyncError):
        ac.CausalReceipt(receipt.revision, replace(receipt.snapshot, committed={'unknown': 1}))
    assert queue.status(endpoint=operation.endpoint, user_id='alice')['pending'] == 1


def test_bounded_stale_rejections_leave_edit_due_for_a_later_drain(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    client, queue, operation, _server, calls, perform = connected(tmp_path, monkeypatch)
    def busy(call):
        if call['method'] == 'PUT':
            calls.append(dict(call))
            return {'status': 409, 'text': json.dumps({'detail': {'revision': 2, 'code': 'stale_revision'}})}
        return perform(call)
    monkeypatch.setattr(http_client, 'perform_call', busy)
    result = client.flush(queue, policy=ac.SyncRetryPolicy(max_attempts=1, backoff=0), max_rebases=2)
    assert result.failed == 1 and result.pending == 1
    assert len([call for call in calls if call['method'] == 'PUT']) == 3
    assert queue.status(endpoint=operation.endpoint, user_id='alice')['offline'] == 1
    assert queue.pending(endpoint=operation.endpoint, user_id='alice')[0].prepared is None


def test_equal_revision_snapshot_fork_cannot_replace_cached_evidence(tmp_path, monkeypatch):
    _client, queue, operation, _server, _calls, _perform = connected(tmp_path, monkeypatch)
    entry = operation.entries[0]
    first = ac.CausalBucket('alice', 1, (entry,), committed={entry.change_id: 1})
    queue.flush(lambda _operation: ac.CausalReceipt(1, first), endpoint=operation.endpoint, user_id='alice')
    other = ac.SyncEntry('settings', 'theme', {'value': 'fork'}, {'desktop': 1}, 'fork', 'desktop')
    fork = ac.CausalBucket('alice', 1, (other,), committed={other.change_id: 1})
    queue.enqueue(replace(operation, operation_id='second', entries=(other,)))
    result = queue.flush(lambda _operation: ac.CausalReceipt(1, fork), endpoint=operation.endpoint, user_id='alice',
                         policy=ac.SyncRetryPolicy(max_attempts=1))
    assert result.delivered == 0 and result.pending == 1
    assert queue.snapshot(endpoint=operation.endpoint, user_id='alice') == first


def test_expired_lease_owner_cannot_publish_a_snapshot_after_its_replacement(tmp_path, monkeypatch):
    _client, _queue, operation, server, _calls, _perform = connected(tmp_path, monkeypatch)
    now = [100.0]
    queue = ac.SyncOutbox(tmp_path / 'outbox.sqlite3', clock=lambda: now[0])
    current = server.get('alice')
    entry = operation.entries[0]
    accepted = replace(current, revision=2, entries=(entry,), committed={entry.change_id: 2})
    later_entry = entry.evolve({'value': 'later'}, origin='desktop', operation_id='later')
    later = replace(current, revision=3, entries=(later_entry,), committed={later_entry.change_id: 3})
    entered, release = Event(), Event()
    def stale(_operation):
        entered.set()
        assert release.wait(5)
        return ac.CausalReceipt(2, later)
    policy = ac.SyncRetryPolicy(lease_seconds=1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(queue.flush, stale, endpoint=operation.endpoint, user_id='alice', policy=policy)
        try:
            assert entered.wait(2)
            now[0] = 102
            replacement = queue.flush(lambda _operation: ac.CausalReceipt(2, accepted),
                                       endpoint=operation.endpoint, user_id='alice', policy=policy)
            assert replacement.delivered == 1
        finally:
            release.set()
        assert future.result().delivered == 0
    assert queue.snapshot(endpoint=operation.endpoint, user_id='alice') == accepted


def test_snapshot_storage_failure_rolls_back_delivery_and_retry_uses_original_receipt(tmp_path, monkeypatch):
    client, queue, operation, server, calls, _perform = connected(tmp_path, monkeypatch)
    original = queue._save_snapshot
    def unavailable(*_args):
        raise ac.ConfigStoreError('controlled snapshot storage failure')
    monkeypatch.setattr(queue, '_save_snapshot', unavailable)
    policy = ac.SyncRetryPolicy(max_attempts=1, backoff=0)
    assert client.flush(queue, policy=policy).pending == 1
    state = queue.status(endpoint=operation.endpoint, user_id='alice')
    assert state['confirmed_revision'] == 0 and state['delivered'] == 0
    assert queue.snapshot(endpoint=operation.endpoint, user_id='alice') is None
    accepted = server.get('alice').revision
    calls.clear()
    monkeypatch.setattr(queue, '_save_snapshot', original)
    assert client.flush(queue, policy=policy).delivered == 1
    assert [call['method'] for call in calls] == ['PUT'] and server.get('alice').revision == accepted


def test_prepared_request_cannot_smuggle_changes_outside_its_logical_operation(tmp_path, monkeypatch):
    client, queue, operation, server, calls, _perform = connected(tmp_path, monkeypatch)
    extra = ac.SyncEntry('settings', 'unrelated', {'value': 'smuggled'}, {'desktop': 1}, 'smuggled', 'desktop')
    current = server.get('alice')
    body = current.with_entries((*operation.entries, extra)).to_dict()
    body['_actor'] = ac.SyncActor('desktop', 0).to_dict()
    queue.prepare(operation, base_revision=current.revision, bucket=body)
    result = client.flush(queue, policy=ac.SyncRetryPolicy(max_attempts=1))
    assert result.pending == 1 and result.delivered == 0 and calls == []
    assert server.get('alice') == current


def test_echoed_live_credential_is_never_persisted_as_a_server_snapshot(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    client, queue, operation, server, calls, perform = connected(tmp_path, monkeypatch)
    entry = ac.SyncEntry('settings', 'echo', {'value': 'synthetic-only'}, {'desktop': 1}, 'echo', 'desktop')
    malicious = replace(server.get('alice'), revision=2, entries=(entry,), committed={entry.change_id: 2})
    def echoed(call):
        if call['method'] == 'PUT':
            calls.append(dict(call))
            return {'status': 200, 'text': json.dumps({'version': 3, 'revision': 2, 'bucket': malicious.to_dict()})}
        return perform(call)
    monkeypatch.setattr(http_client, 'perform_call', echoed)
    result = client.flush(queue, policy=ac.SyncRetryPolicy(max_attempts=1))
    assert result.delivered == 0 and result.pending == 1
    assert queue.snapshot(endpoint=operation.endpoint, user_id='alice') is None
    assert 'synthetic-only' not in str(queue.status(endpoint=operation.endpoint, user_id='alice')['errors'])
    assert b'synthetic-only' not in (tmp_path / 'outbox.sqlite3').read_bytes()


@pytest.mark.parametrize('timeout', [True, 0, -1, float('nan'), float('inf'), '5', 10**1000])
def test_invalid_timeout_fails_before_network_or_database_access(timeout):
    with pytest.raises(ac.ConfigSyncError):
        ac.CausalSyncClient('https://controlled.invalid', user_id='alice', timeout_s=timeout)


def test_shared_control_signals_preserve_mcp_and_history_import_contracts():
    from je_auto_control.utils.exception import control_signals
    from je_auto_control.utils.mcp_server.context import OperationCancelledError
    from je_auto_control.utils.run_history import run_outcome
    assert control_signals.OperationCancelledError is OperationCancelledError
    assert run_outcome.is_run_interruption is control_signals.is_run_interruption
    assert run_outcome.raise_if_run_interrupted is control_signals.raise_if_run_interrupted
    signal = OperationCancelledError('controlled')
    assert isinstance(signal, RuntimeError) and not isinstance(signal, ac.AutoControlException)
    try:
        raise signal
    except OperationCancelledError as cause:
        wrapped = ac.ConfigSyncError('wrapped signal')
        wrapped.__cause__ = cause
    with pytest.raises(OperationCancelledError) as caught:
        control_signals.raise_caused_run_interruption(wrapped)
    assert caught.value is signal
