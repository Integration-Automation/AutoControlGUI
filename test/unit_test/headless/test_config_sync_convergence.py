"""Causal conflicts and durable retry evidence survive offline and restarted clients."""
from threading import Event

import pytest


def entry(value, version, *, origin='a', operation='one', deleted=False, revision=0):
    from je_auto_control.utils.config_sync.versions import SyncEntry
    return SyncEntry(value=value, version=version, origin=origin, operation_id=operation,
                     is_deleted=deleted, deleted_revision=revision)


def test_parallel_edits_preserve_conflict():
    from je_auto_control.utils.config_sync.versions import merge_entries
    left = entry({'combo': 'ctrl+a'}, {'a': 1}, origin='a')
    right = entry({'combo': 'ctrl+b'}, {'b': 1}, origin='b', operation='two')
    conflict = merge_entries(left, right)
    assert conflict.local == left and conflict.remote == right
    assert conflict.conflicted is True and conflict.merged is None


def test_clock_skew_does_not_choose_winner():
    from je_auto_control.utils.config_sync.versions import merge_entries
    left = entry({'combo': 'ctrl+a', 'last_modified': 99999999999}, {'a': 1})
    right = entry({'combo': 'ctrl+b', 'last_modified': 1}, {'b': 1}, origin='b')
    first = merge_entries(left, right)
    second = merge_entries(right, left)
    wall_clock_does_not_change_merge = first.conflicted and second.conflicted
    assert wall_clock_does_not_change_merge is True


def test_causally_later_deletion_does_not_resurrect():
    from je_auto_control.utils.config_sync.versions import merge_entries
    live = entry({'combo': 'ctrl+a'}, {'a': 1})
    tombstone = entry({}, {'a': 2}, deleted=True, revision=4)
    assert tombstone.is_deleted is True
    assert merge_entries(live, tombstone).merged == tombstone
    assert merge_entries(tombstone, live).merged == tombstone


def test_divergent_equal_vectors_are_conflicts():
    from je_auto_control.utils.config_sync.versions import merge_entries
    assert merge_entries(entry({'x': 1}, {'a': 1}), entry({'x': 2}, {'a': 1})).conflicted


def test_json_boolean_and_integer_are_distinct_edits():
    from je_auto_control.utils.config_sync.versions import merge_entries
    assert merge_entries(entry({'enabled': True}, {'a': 1}),
                         entry({'enabled': 1}, {'a': 1})).conflicted


@pytest.mark.parametrize('version', [{'a': -1}, {'a': True}, {'a': 1.5}, {'a': '1'}])
def test_invalid_vector_cannot_claim_causal_dominance(version):
    from je_auto_control.utils.config_sync import ConfigSyncError
    with pytest.raises(ConfigSyncError):
        entry({}, version)


def operation(user='alice', endpoint='https://sync.example', operation_id='stable'):
    from je_auto_control.utils.config_sync.outbox import SyncOperation
    from je_auto_control.utils.config_sync import ConfigBucket
    return SyncOperation(endpoint, user, operation_id, 0, ConfigBucket(user).to_dict())


def outbox(path, user='alice', endpoint='https://sync.example'):
    from je_auto_control.utils.config_sync.outbox import SyncOutbox
    return SyncOutbox(path, endpoint=endpoint, user_id=user)


def test_restart_retries_outbox(tmp_path):
    from je_auto_control.utils.config_sync import ConfigBucket, ConfigStore
    database = ConfigStore(tmp_path / 'server.sqlite')
    pending = outbox(tmp_path / 'outbox.sqlite')
    pending.enqueue(operation())

    def uncertain_write(item):
        database.commit(item.user_id, ConfigBucket.from_dict(item.bucket),
                        base_revision=item.base_revision, operation_id=item.operation_id)
        raise OSError('reply lost')

    assert pending.drain(uncertain_write, now=0).pending == 1
    pending.close()
    reopened = outbox(tmp_path / 'outbox.sqlite')
    assert reopened.pending()[0].operation_id == 'stable'

    def retry(item):
        return database.commit(item.user_id, ConfigBucket.from_dict(item.bucket),
                               base_revision=item.base_revision, operation_id=item.operation_id)

    assert reopened.drain(retry, now=1000).sent == 1
    assert reopened.pending() == ()
    assert database.get('alice').revision == 1
    reopened.close()
    database.close()


def test_outbox_account_and_endpoint_isolation(tmp_path):
    path = tmp_path / 'outbox.sqlite'
    alice = outbox(path)
    bob = outbox(path, user='bob')
    another = outbox(path, endpoint='https://another.example')
    alice.enqueue(operation())
    assert bob.pending() == () and another.pending() == ()
    for instance in (alice, bob, another):
        instance.close()


def test_cancel_and_bounded_retry_do_not_drop_pending_data(tmp_path):
    pending = outbox(tmp_path / 'outbox.sqlite')
    pending.enqueue(operation())
    cancelled = Event()
    cancelled.set()
    assert pending.drain(lambda _item: pytest.fail('cancelled send'), cancel=cancelled, now=0).cancelled
    assert len(pending.pending()) == 1
    calls = []

    def failure(_item):
        calls.append(True)
        raise OSError('offline')

    for now in range(0, 10000, 1000):
        pending.drain(failure, now=now, max_attempts=3)
    assert len(calls) == 3
    assert pending.pending()[0].operation_id == 'stable'
    pending.close()


def test_retired_peer_requires_full_sync(tmp_path):
    path = tmp_path / 'outbox.sqlite'
    pending = outbox(path)
    pending.acknowledge_peer('laptop', revision=4)
    pending.retire_peer('laptop')
    pending.close()
    reopened = outbox(path)
    assert reopened.requires_full_sync('laptop') is True
    reopened.complete_full_sync('laptop', revision=6)
    assert reopened.requires_full_sync('laptop') is False
    reopened.close()


def test_tombstones_require_every_active_peer_acknowledgement():
    from je_auto_control.utils.config_sync.versions import PeerState, can_collect_tombstone
    tombstone = entry({}, {'a': 2}, deleted=True, revision=5)
    assert not can_collect_tombstone(tombstone, [PeerState('a', 5), PeerState('b', 4)])
    assert can_collect_tombstone(tombstone, [PeerState('a', 5), PeerState('b', 5)])
    assert not can_collect_tombstone(tombstone, [])


def test_outbox_does_not_accept_an_uncommitted_revision(tmp_path):
    pending = outbox(tmp_path / 'outbox.sqlite')
    pending.enqueue(operation())
    assert pending.drain(lambda _item: 0, now=0).sent == 0
    assert len(pending.pending()) == 1
    pending.close()


def test_causal_bucket_merge_retains_all_conflict_alternatives():
    from je_auto_control.utils.config_sync import ConfigBucket
    from je_auto_control.utils.config_sync.causal_bucket import causal_upsert, merge_causal_buckets
    left, right = ConfigBucket('alice'), ConfigBucket('alice')
    causal_upsert(left, 'hotkeys', 'one', {'combo': 'ctrl+a'}, device_id='a')
    causal_upsert(right, 'hotkeys', 'one', {'combo': 'ctrl+b'}, device_id='b')
    merged, conflicts = merge_causal_buckets(left, right)
    mirrored, _ = merge_causal_buckets(right, left)
    assert len(conflicts) == 1
    assert merged.to_dict() == mirrored.to_dict()
    assert merged.entries('hotkeys') == {}
    alternatives = merged.sections['hotkeys']['one']['sync_conflict']
    assert {item['combo'] for item in alternatives} == {'ctrl+a', 'ctrl+b'}
    again, _ = merge_causal_buckets(merged, left)
    assert again.sections['hotkeys']['one']['sync_conflict'] == alternatives


def test_client_protected_push_and_uncertain_retry(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from je_auto_control.utils.config_sync import ConfigBucket, ConfigSyncClient, ConfigSyncError
    from je_auto_control.utils.config_sync.client import SyncClientOptions
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    from je_auto_control.utils.http_client import http_client
    app = create_app(shared_secret='secret', serve_web_viewer=False,
                     config_store_path=tmp_path / 'server.sqlite')
    lost = [True]

    with TestClient(app) as server:
        def perform(call):
            response = server.request(call['method'], call['url'], headers=call['headers'], content=call['body'])
            if call['method'] == 'PUT' and lost[0]:
                lost[0] = False
                raise OSError('reply lost after server commit')
            return {'status': response.status_code, 'text': response.text}

        monkeypatch.setattr(http_client, 'perform_call', perform)
        options = SyncClientOptions(outbox_path=tmp_path / 'outbox.sqlite', device_id='a')
        sync = ConfigSyncClient('http://testserver', user_id='alice', secret='secret', options=options)
        with pytest.raises(ConfigSyncError):
            sync.push(ConfigBucket('alice'), operation_id='stable')
        sync.close()
        reopened = ConfigSyncClient('http://testserver', user_id='alice', secret='secret', options=options)
        assert reopened.retry_pending().sent == 1
        assert reopened.fetch().revision == 1
        assert reopened.pending_operations() == ()
        assert b'secret' not in (tmp_path / 'outbox.sqlite').read_bytes()
        reopened.close()


@pytest.fixture
def config_server(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    from je_auto_control.utils.http_client import http_client
    app = create_app(serve_web_viewer=False, config_store_path=tmp_path / 'server.sqlite')
    with TestClient(app) as server:
        def perform(call):
            response = server.request(call['method'], call['url'], headers=call['headers'], content=call['body'])
            return {'status': response.status_code, 'text': response.text}
        monkeypatch.setattr(http_client, 'perform_call', perform)
        yield server


def sync_client(tmp_path, device):
    from je_auto_control.utils.config_sync import ConfigSyncClient
    from je_auto_control.utils.config_sync.client import SyncClientOptions
    return ConfigSyncClient('http://testserver', user_id='alice',
                            options=SyncClientOptions(outbox_path=tmp_path / f'{device}.sqlite', device_id=device))


def test_shared_peer_acknowledgements_prevent_early_deletion_gc(tmp_path, config_server):
    from je_auto_control.utils.config_sync import ConfigBucket
    from je_auto_control.utils.config_sync.causal_bucket import (
        causal_upsert, causal_remove, collect_acknowledged_tombstones, bucket_peer_states,
    )
    a, b = sync_client(tmp_path, 'a'), sync_client(tmp_path, 'b')
    local = ConfigBucket('alice')
    causal_upsert(local, 'hotkeys', 'one', {'combo': 'ctrl+a'}, device_id='a')
    local, _ = a.sync(local)
    stale, _ = b.sync(ConfigBucket('alice'))
    assert causal_remove(local, 'hotkeys', 'one', device_id='a')
    assert local.sections['hotkeys']['one']['_sync']['deleted_revision'] == 0
    deleted, _ = a.sync(local)
    retained = collect_acknowledged_tombstones(deleted, bucket_peer_states(deleted))
    assert retained.sections['hotkeys']['one']['deleted'] is True
    acknowledged, _ = b.sync(stale)
    assert acknowledged.entries('hotkeys') == {}
    collected = collect_acknowledged_tombstones(acknowledged, bucket_peer_states(acknowledged))
    assert collected.sections['hotkeys'] == {}
    a.close()
    b.close()


def test_server_retired_device_cannot_incrementally_resurrect(tmp_path, config_server):
    from je_auto_control.utils.config_sync import ConfigBucket, ConfigSyncError
    from je_auto_control.utils.config_sync.causal_bucket import causal_upsert, causal_remove
    a, b = sync_client(tmp_path, 'a'), sync_client(tmp_path, 'b')
    local = ConfigBucket('alice')
    causal_upsert(local, 'hotkeys', 'one', {'combo': 'ctrl+a'}, device_id='a')
    local, _ = a.sync(local)
    stale, _ = b.sync(ConfigBucket('alice'))
    causal_remove(local, 'hotkeys', 'one', device_id='a')
    a.sync(local)
    a.retire_device('b')
    with pytest.raises(ConfigSyncError, match='full sync'):
        b.sync(stale)
    snapshot = b.full_resync()
    assert snapshot.entries('hotkeys') == {}
    assert b.sync(snapshot)[0].entries('hotkeys') == {}
    a.close()
    b.close()


def test_unresolved_retirement_cannot_be_silently_reactivated(tmp_path, config_server):
    from je_auto_control.utils.config_sync import ConfigBucket, ConfigSyncError
    variants = []
    for device, retired in [('a', True), ('b', False)]:
        variants.append({'acknowledged_revision': 1, 'retired': retired,
                         '_sync': {'version': {device: 1}, 'origin': device,
                                   'operation_id': device, 'deleted_revision': 0}})
    bucket = ConfigBucket('alice', {'__sync_devices__': {'b': {'sync_conflict': variants}}})
    config_server.put('/config/alice', json={'schema_version': 2, 'base_revision': 0,
                                           'operation_id': 'initial', 'bucket': bucket.to_dict()})
    b = sync_client(tmp_path, 'b')
    with pytest.raises(ConfigSyncError, match='full sync'):
        b.sync(ConfigBucket('alice'))
    b.close()


def test_retired_device_cannot_push_an_old_snapshot(tmp_path, config_server):
    from je_auto_control.utils.config_sync import ConfigBucket, ConfigSyncError
    a, b = sync_client(tmp_path, 'a'), sync_client(tmp_path, 'b')
    a.sync(ConfigBucket('alice'))
    stale, _ = b.sync(ConfigBucket('alice'))
    a.retire_device('b')
    current_revision = config_server.get('/config/alice').json()['revision']
    with pytest.raises(ConfigSyncError, match='full sync'):
        b.push(stale, base_revision=current_revision)
    assert config_server.get('/config/alice').json()['revision'] == current_revision
    a.close()
    b.close()


def test_cas_race_refetches_and_preserves_both_edits(tmp_path, config_server, monkeypatch):
    from je_auto_control.utils.config_sync import ConfigBucket
    from je_auto_control.utils.config_sync.causal_bucket import causal_upsert
    from je_auto_control.utils.http_client import http_client
    local, rival = ConfigBucket('alice'), ConfigBucket('alice')
    causal_upsert(local, 'hotkeys', 'one', {'combo': 'ctrl+a'}, device_id='a')
    causal_upsert(rival, 'hotkeys', 'one', {'combo': 'ctrl+b'}, device_id='b')
    transport = http_client.perform_call
    interleaved = [False]

    def perform(call):
        if call['method'] == 'PUT' and not interleaved[0]:
            interleaved[0] = True
            config_server.put('/config/alice', json={'schema_version': 2, 'base_revision': 0,
                                                   'operation_id': 'rival', 'bucket': rival.to_dict()})
        return transport(call)

    monkeypatch.setattr(http_client, 'perform_call', perform)
    sync = sync_client(tmp_path, 'a')
    merged, conflicts = sync.sync(local)
    assert merged.revision == 2 and len(conflicts) == 1
    alternatives = config_server.get('/config/alice').json()['sections']['hotkeys']['one']['sync_conflict']
    assert {item['combo'] for item in alternatives} == {'ctrl+a', 'ctrl+b'}
    assert sync.pending_operations() == ()
    sync.close()
