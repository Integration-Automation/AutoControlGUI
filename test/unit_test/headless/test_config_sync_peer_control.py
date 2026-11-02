"""Durable peer controls register, acknowledge and adopt full snapshots without reviving obsolete edits."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from threading import Event

import pytest

import je_auto_control as ac
from headless.test_config_sync_causal_store import actor, register
from headless.causal_transport import perform_causal_call


def peer(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    server = ac.CausalConfigStore(tmp_path / 'server.sqlite3')
    queue = ac.SyncOutbox(tmp_path / 'outbox.sqlite3')
    endpoint = 'https://controlled.invalid'
    queue.identity(endpoint, 'alice', origin='desktop')
    client = ac.CausalSyncClient(endpoint, user_id='alice')
    calls = []
    def perform(call):
        calls.append(dict(call))
        return perform_causal_call(server, call)
    monkeypatch.setattr(http_client, 'perform_call', perform)
    return client, queue, server, calls, perform


def edit(queue, *, epoch=0, operation_id='edit'):
    entry = ac.SyncEntry('settings', 'theme', {'value': 'dark'}, {'desktop': 1}, operation_id, 'desktop')
    operation = ac.SyncOperation(operation_id, 'https://controlled.invalid', 'alice', 'desktop', (entry,), epoch=epoch)
    queue.enqueue(operation)
    return operation


def test_register_preserves_initial_offline_edits_then_flushes_them(tmp_path, monkeypatch):
    client, queue, server, _calls, _perform = peer(tmp_path, monkeypatch)
    operation = edit(queue)
    result = client.control(queue, 'register')
    assert result.delivered == 1 and result.pending == 0 and result.revision == 1
    assert queue.pending(endpoint=operation.endpoint, user_id='alice') == (operation,)
    assert queue.snapshot(endpoint=operation.endpoint, user_id='alice') == server.get('alice')
    assert client.flush(queue).delivered == 1
    assert server.get('alice').live_entries == operation.entries


def test_registration_resumes_same_epoch_edits_blocked_before_the_peer_existed(tmp_path, monkeypatch):
    client, queue, server, _calls, _perform = peer(tmp_path, monkeypatch)
    operation = edit(queue)
    assert client.flush(queue).pending == 1
    assert queue.status(endpoint=operation.endpoint, user_id='alice')['blocked'] == 1
    assert client.control(queue, 'register').delivered == 1
    assert queue.identity(operation.endpoint, 'alice').epoch == 0
    assert client.flush(queue).delivered == 1
    assert server.get('alice').live_entries == operation.entries


def test_ack_and_collection_wait_for_every_active_peer(tmp_path, monkeypatch):
    client, queue, server, _calls, _perform = peer(tmp_path, monkeypatch)
    client.control(queue, 'register')
    register(server, 'laptop')
    operation = edit(queue)
    client.flush(queue)
    deleted = operation.entries[0].evolve({'value': 'dark'}, origin='desktop', operation_id='delete', is_deleted=True)
    queue.enqueue(ac.SyncOperation('delete', operation.endpoint, 'alice', 'desktop', (deleted,)))
    client.flush(queue)
    deletion_revision = server.get('alice').revision
    client.control(queue, 'ack')
    client.control(queue, 'collect')
    assert server.get('alice').entries == (deleted,)
    other = ac.SyncOutbox(tmp_path / 'laptop.sqlite3')
    other.identity(operation.endpoint, 'alice', origin='laptop')
    client.control(other, 'ack')
    client.control(queue, 'collect')
    final = server.get('alice')
    assert final.entries == () and len(final.fences) == 1
    assert final.fences[0].deletion_revision == deletion_revision


def test_full_resync_requires_explicit_pending_retirement_and_adopts_new_epoch(tmp_path, monkeypatch):
    client, queue, server, calls, _perform = peer(tmp_path, monkeypatch)
    client.control(queue, 'register')
    operation = edit(queue)
    state = server.get('alice')
    peers = state.peers
    peers.retire('desktop')
    server.commit('alice', state.with_peers(peers), base_revision=state.revision,
                  operation_id='retire', actor=actor('desktop', 'retire', peer_id='desktop'))
    assert client.flush(queue).pending == 1
    before = len(calls)
    with pytest.raises(ac.ConfigSyncError):
        client.control(queue, 'full_resync')
    assert len(calls) == before
    result = client.control(queue, 'full_resync', discard_pending=True)
    assert result.delivered == 1 and result.pending == 0
    assert queue.identity(operation.endpoint, 'alice').epoch == 1
    assert queue.status(endpoint=operation.endpoint, user_id='alice')['retired'] == 1
    assert queue.pending(endpoint=operation.endpoint, user_id='alice') == ()
    assert queue.snapshot(endpoint=operation.endpoint, user_id='alice') == server.get('alice')
    with pytest.raises(ac.FullResyncRequired):
        edit(queue, operation_id='obsolete')
    fresh = edit(queue, epoch=1, operation_id='fresh')
    assert client.flush(queue).delivered == 1 and server.get('alice').live_entries == fresh.entries


def test_uncertain_register_replays_exact_control_before_fetch_after_restart(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    client, queue, server, calls, perform = peer(tmp_path, monkeypatch)
    first = [True]
    def uncertain(call):
        response = perform(call)
        if call['method'] == 'PUT' and first[0]:
            first[0] = False
            raise OSError('controlled loss after peer registration')
        return response
    monkeypatch.setattr(http_client, 'perform_call', uncertain)
    result = client.control(queue, 'register', policy=ac.SyncRetryPolicy(max_attempts=1, backoff=0))
    assert result.pending == 1 and result.delivered == 0
    assert server.get('alice').revision == 1
    original_body = next(call['body'] for call in calls if call['method'] == 'PUT')
    calls.clear()
    reopened = ac.SyncOutbox(tmp_path / 'outbox.sqlite3')
    client.flush(reopened, policy=ac.SyncRetryPolicy(max_attempts=1, backoff=0))
    assert [call['method'] for call in calls] == ['PUT'] and calls[0]['body'] == original_body
    assert reopened.control_status(endpoint='https://controlled.invalid', user_id='alice')['state'] == 'delivered'


def test_uncertain_resync_keeps_old_edits_until_receipt_is_durably_adopted(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    client, queue, _server, calls, perform = peer(tmp_path, monkeypatch)
    client.control(queue, 'register')
    operation = edit(queue)
    first = [True]
    def uncertain(call):
        response = perform(call)
        if call['method'] == 'PUT' and first[0]:
            first[0] = False
            raise OSError('controlled loss after peer epoch change')
        return response
    monkeypatch.setattr(http_client, 'perform_call', uncertain)
    result = client.control(queue, 'full_resync', discard_pending=True,
                            policy=ac.SyncRetryPolicy(max_attempts=1, backoff=0))
    assert result.pending == 1 and queue.identity(operation.endpoint, 'alice').epoch == 0
    assert queue.status(endpoint=operation.endpoint, user_id='alice')['retired'] == 0
    queue.enqueue(operation)
    with pytest.raises(ac.FullResyncRequired):
        edit(queue, operation_id='during-resync')
    calls.clear()
    reopened = ac.SyncOutbox(tmp_path / 'outbox.sqlite3')
    client.flush(reopened, policy=ac.SyncRetryPolicy(max_attempts=1, backoff=0))
    assert [call['method'] for call in calls] == ['PUT']
    assert reopened.identity(operation.endpoint, 'alice').epoch == 1
    assert reopened.status(endpoint=operation.endpoint, user_id='alice')['retired'] == 1


def test_old_sending_callback_cannot_replace_the_adopted_epoch_snapshot(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    client, queue, server, _calls, perform = peer(tmp_path, monkeypatch)
    client.control(queue, 'register')
    operation = edit(queue)
    entered, release = Event(), Event()
    first = [True]
    def held_reply(call):
        response = perform(call)
        if call['method'] == 'PUT' and first[0]:
            first[0] = False
            entered.set()
            assert release.wait(8)
        return response
    monkeypatch.setattr(http_client, 'perform_call', held_reply)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.flush, queue)
        try:
            assert entered.wait(3)
            assert client.control(queue, 'full_resync', discard_pending=True).delivered == 1
            current = queue.snapshot(endpoint=operation.endpoint, user_id='alice')
            assert current.peers.require_active('desktop', epoch=1)
        finally:
            release.set()
        assert pending.result().delivered == 0
    assert queue.snapshot(endpoint=operation.endpoint, user_id='alice') == current == server.get('alice')


def test_a_live_control_lease_prevents_a_second_worker_from_sending_the_same_intent(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    client, queue, _server, calls, perform = peer(tmp_path, monkeypatch)
    entered, release = Event(), Event()
    def held_reply(call):
        response = perform(call)
        if call['method'] == 'PUT':
            entered.set()
            assert release.wait(6)
        return response
    monkeypatch.setattr(http_client, 'perform_call', held_reply)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.control, queue, 'register')
        try:
            assert entered.wait(3)
            second = client.control(ac.SyncOutbox(tmp_path / 'outbox.sqlite3'), 'register')
            assert second.delivered == 0 and second.pending == 1
            assert [call['method'] for call in calls] == ['GET', 'PUT']
        finally:
            release.set()
        assert first.result().delivered == 1


def test_pre_cancelled_peer_control_never_opens_an_outbox(tmp_path):
    path = tmp_path / 'never-opened.sqlite3'
    client = ac.CausalSyncClient('https://controlled.invalid', user_id='alice')
    with pytest.raises(CancelledError):
        client.control(ac.SyncOutbox(path), 'register', cancelled=lambda: True)
    assert not path.exists()


def test_owned_version_one_database_migrates_without_changing_old_edit_wires(tmp_path):
    from dataclasses import replace
    from hashlib import sha256
    import json
    import sqlite3
    from je_auto_control.utils.config_sync.outbox_schema import _APPLICATION, _TABLES
    path = tmp_path / 'version-one.sqlite3'
    endpoint = 'https://controlled.invalid'
    entry = ac.SyncEntry('settings', 'theme', {'value': 'dark'}, {'desktop': 1}, 'edit', 'desktop')
    operation = ac.SyncOperation('edit', endpoint, 'alice', 'desktop', (entry,))
    body = operation.to_dict()
    encoded = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    prepared = {'base_revision': 0, 'bucket': ac.ConfigBucket('alice').to_dict()}
    with sqlite3.connect(path) as connection:
        for statement in _TABLES:
            connection.execute(statement)
        connection.execute(f'PRAGMA application_id={_APPLICATION}')
        connection.execute('PRAGMA user_version=1')
        connection.execute('INSERT INTO sync_namespaces (endpoint,user_id,origin,epoch) VALUES (?,?,?,?)',
                           (endpoint, 'alice', 'desktop', 0))
        connection.execute('INSERT INTO sync_operations (endpoint,user_id,operation_id,wire,digest,prepared) '
                           'VALUES (?,?,?,?,?,?)', (endpoint, 'alice', 'edit', encoded,
                                                  sha256(encoded.encode('ascii')).hexdigest(), json.dumps(prepared)))
    queue = ac.SyncOutbox(path)
    assert queue.pending(endpoint=endpoint, user_id='alice') == (replace(operation, prepared=prepared),)
    assert queue.control_status(endpoint=endpoint, user_id='alice')['state'] == 'idle'
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 3
        assert connection.execute('SELECT wire FROM sync_operations').fetchone()[0] == encoded


def test_metadata_stale_cas_budget_preserves_the_control_for_later_retry(tmp_path, monkeypatch):
    import json
    from je_auto_control.utils.http_client import http_client
    client, queue, _server, calls, perform = peer(tmp_path, monkeypatch)
    client.control(queue, 'register')
    calls.clear()
    def busy(call):
        if call['method'] == 'PUT':
            calls.append(dict(call))
            return {'status': 409, 'text': json.dumps({'detail': {'code': 'stale_revision', 'revision': 2}})}
        return perform(call)
    monkeypatch.setattr(http_client, 'perform_call', busy)
    policy = ac.SyncRetryPolicy(max_attempts=1, backoff=0)
    result = client.control(queue, 'ack', policy=policy)
    assert result.pending == 1 and result.failed == 1 and result.delivered == 0
    requests = [json.loads(call['body']) for call in calls if call['method'] == 'PUT']
    assert len(requests) == 4 and len({request['operation_id'] for request in requests}) == 1
    assert queue.control_status(endpoint='https://controlled.invalid', user_id='alice')['state'] == 'offline'
    monkeypatch.setattr(http_client, 'perform_call', perform)
    assert client.flush(queue, policy=policy).pending == 0


def test_full_resync_after_server_reset_rotates_local_origin_and_adopts_authoritative_revision(tmp_path, monkeypatch):
    import sqlite3
    client, queue, server, _calls, _perform = peer(tmp_path, monkeypatch)
    client.control(queue, 'register')
    operation = edit(queue)
    client.flush(queue)
    with sqlite3.connect(tmp_path / 'server.sqlite3') as connection:
        connection.execute('DELETE FROM config_operations')
        connection.execute('DELETE FROM config_buckets')
    result = client.control(queue, 'full_resync', discard_pending=True)
    assert result.delivered == 1 and result.revision == 1
    identity = queue.identity(operation.endpoint, 'alice')
    assert identity.origin != 'desktop' and identity.epoch == 0 and identity.confirmed_revision == 1
    assert queue.snapshot(endpoint=operation.endpoint, user_id='alice') == server.get('alice')
    assert server.get('alice').live_entries == ()


def test_control_receipt_conflict_requires_explicit_recovery_instead_of_rebasing(tmp_path, monkeypatch):
    import json
    from je_auto_control.utils.http_client import http_client
    client, queue, server, calls, perform = peer(tmp_path, monkeypatch)
    first = [True]
    def conflicting(call):
        if call['method'] == 'PUT' and first[0]:
            first[0] = False
            request = json.loads(call['body'])
            current = server.get('alice')
            peers = current.peers
            peers.register('other', full_revision=current.revision)
            server.commit('alice', current.with_peers(peers), base_revision=current.revision,
                          operation_id=request['operation_id'], actor=actor('other', 'full_sync', revision=0))
        return perform(call)
    monkeypatch.setattr(http_client, 'perform_call', conflicting)
    result = client.control(queue, 'register')
    assert result.pending == 1 and result.delivered == 0
    assert [call['method'] for call in calls] == ['GET', 'PUT']
    assert queue.control_status(endpoint='https://controlled.invalid', user_id='alice')['state'] == 'conflict'
    assert client.control(queue, 'full_resync').delivered == 1


def test_historical_control_request_id_never_retires_work_queued_after_its_first_completion(tmp_path, monkeypatch):
    client, queue, server, calls, _perform = peer(tmp_path, monkeypatch)
    client.control(queue, 'register')
    edit(queue)
    request = ac.SyncControlRequest('full_resync', operation_id='reviewed-resync', discard_pending=True)
    original = client.control(queue, request)
    assert original.delivered == 1
    fresh = edit(queue, epoch=1, operation_id='fresh')
    client.control(queue, 'ack')
    queue = ac.SyncOutbox(tmp_path / 'outbox.sqlite3')
    before_calls, before_revision = len(calls), server.get('alice').revision
    repeated = client.control(queue, request)
    assert repeated.revision == original.revision and repeated.pending == 0
    assert len(calls) == before_calls and server.get('alice').revision == before_revision
    assert queue.pending(endpoint=fresh.endpoint, user_id='alice') == (fresh,)
    with pytest.raises(ac.ConfigSyncError):
        client.control(queue, ac.SyncControlRequest('ack', operation_id='reviewed-resync'))


def test_adoption_and_pending_retirement_roll_back_when_local_receipt_storage_fails(tmp_path, monkeypatch):
    import sqlite3
    client, queue, _server, calls, _perform = peer(tmp_path, monkeypatch)
    client.control(queue, 'register')
    operation = edit(queue)
    with sqlite3.connect(tmp_path / 'outbox.sqlite3') as connection:
        connection.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON sync_control_receipts "
                           "BEGIN SELECT RAISE(ABORT,'controlled receipt failure'); END")
    result = client.control(queue, 'full_resync', discard_pending=True,
                            policy=ac.SyncRetryPolicy(max_attempts=1, backoff=0))
    assert result.pending == 1 and result.delivered == 0
    assert queue.identity(operation.endpoint, 'alice').epoch == 0
    assert queue.status(endpoint=operation.endpoint, user_id='alice')['retired'] == 0
    assert queue.pending(endpoint=operation.endpoint, user_id='alice') == (operation,)
    with sqlite3.connect(tmp_path / 'outbox.sqlite3') as connection:
        connection.execute('DROP TRIGGER reject_receipt')
    calls.clear()
    assert client.flush(queue).pending == 0
    assert [call['method'] for call in calls] == ['PUT']
    assert queue.identity(operation.endpoint, 'alice').epoch == 1
    assert queue.status(endpoint=operation.endpoint, user_id='alice')['retired'] == 1


def test_invalid_owned_version_one_schema_is_refused_before_migration_writes(tmp_path):
    import sqlite3
    from je_auto_control.utils.config_sync.outbox_schema import _APPLICATION
    path = tmp_path / 'not-valid-owned.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute(f'PRAGMA application_id={_APPLICATION}')
        connection.execute('PRAGMA user_version=1')
        connection.execute('CREATE TABLE important (value TEXT)')
        connection.execute("INSERT INTO important VALUES ('preserve')")
    with pytest.raises(ac.ConfigStoreError):
        ac.SyncOutbox(path).status(endpoint='https://controlled.invalid', user_id='alice')
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 1
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [('important',)]
        assert connection.execute('SELECT value FROM important').fetchone()[0] == 'preserve'
