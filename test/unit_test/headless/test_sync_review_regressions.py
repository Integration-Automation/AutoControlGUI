"""Whole-C service recovery, deletion evidence and clipboard behavior regressions."""
import json

import pytest

from je_auto_control.utils.config_sync import ConfigBucket, ConfigStore, ConfigSyncClient, ConfigSyncError
from je_auto_control.utils.config_sync.causal_bucket import causal_upsert, merge_causal_buckets, prepare_tombstone_revisions
from je_auto_control.utils.config_sync.client import SyncClientOptions
from je_auto_control.utils.config_sync.service import config_sync_apply, config_sync_exchange, config_sync_retry, _paths
from je_auto_control.utils.remote_desktop.clipboard_sync import ClipboardLoopGuard, encode_text

ENDPOINT = 'http://sync.example.test'
ACCOUNT = 'review-account'


@pytest.fixture
def sync_store(tmp_path, monkeypatch):
    """Use real SQLite CAS; replace only the network request boundary."""
    store = ConfigStore(tmp_path / 'server.sqlite')
    failure = {'offline': False, 'put': False}

    def request(client, method, *, body=None):
        if failure['offline'] or (method == 'PUT' and failure['put']):
            raise ConfigSyncError('controlled network outage before delivery')
        if method == 'GET':
            bucket = store.get(client._user_id)
            return None if bucket is None else {**bucket.to_dict(), 'schema_version': 2, 'cas_supported': True}
        assert method == 'PUT'
        revision = store.commit(client._user_id, ConfigBucket.from_dict(body['bucket']),
                                base_revision=body['base_revision'], operation_id=body['operation_id'])
        return {'revision': revision, 'schema_version': 2, 'cas_supported': True}

    monkeypatch.setattr(ConfigSyncClient, '_request', request)
    yield store, failure
    store.close()


def write_definitions(path, entries):
    path.write_text(json.dumps({'scripts': entries}), encoding='utf-8')


def exchange(path, workspace):
    return config_sync_exchange(str(path), str(workspace), ENDPOINT, ACCOUNT)


def apply(path, report):
    return config_sync_apply(str(path), report['preview_path'], report['state_path'], report['device_id'])


def test_unapplied_deletion_survives_exchange_and_eventually_collects(tmp_path, sync_store):
    store, _failure = sync_store
    a, b = tmp_path / 'a.json', tmp_path / 'b.json'
    a_workspace, b_workspace = tmp_path / 'a', tmp_path / 'b'
    write_definitions(a, {'x': {'label': 'portable'}})
    write_definitions(b, {})
    exchange(a, a_workspace)
    apply(b, exchange(b, b_workspace))
    write_definitions(b, {})
    apply(b, exchange(b, b_workspace))
    exchange(a, a_workspace)
    exchange(b, b_workspace)
    latest = exchange(a, a_workspace)
    assert latest['conflicts'] == 0
    assert store.get(ACCOUNT).entries('scripts') == {}
    assert json.loads(a.read_text(encoding='utf-8'))['scripts']['x'] == {'label': 'portable'}
    assert store.get(ACCOUNT).sections['scripts']['x']['deleted'] is True
    apply(a, latest)
    exchange(a, a_workspace)
    exchange(b, b_workspace)
    assert store.get(ACCOUNT).sections.get('scripts', {}) == {}


def test_same_deletion_receipt_does_not_create_a_conflict():
    from je_auto_control.utils.config_sync.causal_bucket import causal_remove
    bucket = ConfigBucket(ACCOUNT)
    causal_upsert(bucket, 'scripts', 'x', {'label': 'portable'}, device_id='a')
    causal_remove(bucket, 'scripts', 'x', device_id='a')
    committed = prepare_tombstone_revisions(bucket, 4)
    for left, right in ((bucket, committed), (committed, bucket)):
        merged, conflicts = merge_causal_buckets(left, right)
        assert conflicts == []
        assert merged.sections['scripts']['x']['_sync']['deleted_revision'] == 5


def test_repeated_local_deletion_exchange_needs_no_resolution(tmp_path, sync_store):
    definitions, workspace = tmp_path / 'definitions.json', tmp_path / 'workspace'
    write_definitions(definitions, {'x': {'label': 'portable'}})
    exchange(definitions, workspace)
    write_definitions(definitions, {})
    exchange(definitions, workspace)
    assert exchange(definitions, workspace)['conflicts'] == 0


def make_client(path, device):
    return ConfigSyncClient(ENDPOINT, user_id=ACCOUNT,
                            options=SyncClientOptions(outbox_path=path, device_id=device))


def test_confirmed_stale_outbox_rebases_without_losing_either_edit(tmp_path, sync_store):
    _store, failure = sync_store
    a, b = make_client(tmp_path / 'a.sqlite', 'a'), make_client(tmp_path / 'b.sqlite', 'b')
    local, rival = ConfigBucket(ACCOUNT), ConfigBucket(ACCOUNT)
    causal_upsert(local, 'scripts', 'local', {'label': 'a'}, device_id='a')
    causal_upsert(rival, 'scripts', 'rival', {'label': 'b'}, device_id='b')
    try:
        failure['put'] = True
        with pytest.raises(ConfigSyncError):
            a.sync(local)
        exact = a.pending_operations()[0].envelope()
        failure['put'] = False
        b.sync(rival)
        merged, conflicts = a.sync(local)
        assert conflicts == [] and set(merged.entries('scripts')) == {'local', 'rival'}
        assert a.pending_operations() == ()
        assert exact['operation_id'] != ''
    finally:
        a.close()
        b.close()


def test_explicit_retry_recovers_exhausted_exact_envelope(tmp_path, sync_store):
    _store, _failure = sync_store
    workspace = tmp_path / 'workspace'
    _state, _preview, outbox = _paths(str(workspace), ENDPOINT, ACCOUNT)
    client = make_client(outbox, 'a')
    from je_auto_control.utils.config_sync.outbox import SyncOperation
    bucket = ConfigBucket(ACCOUNT)
    causal_upsert(bucket, 'scripts', 'x', {'label': 'portable'}, device_id='a')
    exact = SyncOperation(ENDPOINT, ACCOUNT, 'unchanged-exhausted-ID', 0, bucket.to_dict())
    client._outbox.enqueue(exact)

    def outage(_operation):
        raise OSError('offline')

    client._outbox.drain(outage, now=0, max_attempts=2)
    client._outbox.drain(outage, now=1000, max_attempts=2)
    assert client.pending_operations()[0].envelope() == exact.envelope()
    client.close()
    report = config_sync_retry(str(workspace), ENDPOINT, ACCOUNT)
    assert report['sent'] == 1 and report['pending'] == 0
    assert sync_store[0].get(ACCOUNT).entries('scripts')['x']['label'] == 'portable'


def test_fully_offline_exchange_is_published_by_retry(tmp_path, sync_store):
    store, failure = sync_store
    path, workspace = tmp_path / 'definitions.json', tmp_path / 'workspace'
    write_definitions(path, {'x': {'label': 'portable'}})
    failure['offline'] = True
    report = exchange(path, workspace)
    assert report['offline'] is True and report['pending'] == 1
    failure['offline'] = False
    retried = config_sync_retry(str(workspace), ENDPOINT, ACCOUNT)
    assert retried['sent'] == 1 and retried['pending'] == 0
    assert store.get(ACCOUNT).entries('scripts')['x']['label'] == 'portable'


def test_legacy_clipboard_can_repeat_after_intervening_content():
    guard = ClipboardLoopGuard()
    assert guard.receive(encode_text('A')) == ('text', 'A')
    assert guard.receive(encode_text('A')) is None
    assert guard.receive(encode_text('B')) == ('text', 'B')
    assert guard.receive(encode_text('A')) == ('text', 'A')


def test_clipboard_echo_expires_when_local_content_changes():
    guard = ClipboardLoopGuard()
    assert guard.receive(encode_text('A')) == ('text', 'A')
    assert guard.encode_text('B') is not None
    assert guard.encode_text('A') is not None


def test_legacy_receive_after_different_local_value_is_new_content():
    guard = ClipboardLoopGuard()
    assert guard.receive(encode_text('A')) == ('text', 'A')
    guard.encode_text('B')
    assert guard.receive(encode_text('A')) == ('text', 'A')


def test_stale_deletion_rebase_does_not_acknowledge_an_uncommitted_receipt(tmp_path, sync_store):
    from je_auto_control.utils.config_sync.causal_bucket import causal_remove
    store, failure = sync_store
    a, b = make_client(tmp_path / 'a.sqlite', 'a'), make_client(tmp_path / 'b.sqlite', 'b')
    try:
        local = ConfigBucket(ACCOUNT)
        causal_upsert(local, 'scripts', 'x', {'label': 'portable'}, device_id='a')
        local, _ = a.sync(local)
        causal_remove(local, 'scripts', 'x', device_id='a')
        failure['put'] = True
        with pytest.raises(ConfigSyncError):
            a.sync(local)
        failure['put'] = False
        b.sync(store.get(ACCOUNT))
        a.retry_pending()
        current = store.get(ACCOUNT)
        assert current.entries('scripts') == {}
        assert current.sections['scripts']['x']['_sync']['deleted_revision'] == current.revision
    finally:
        a.close()
        b.close()


def test_offline_intent_merges_remote_deletion_before_dispatch(tmp_path, sync_store):
    store, failure = sync_store
    a, b = tmp_path / 'a.json', tmp_path / 'b.json'
    a_workspace, b_workspace = tmp_path / 'a', tmp_path / 'b'
    write_definitions(a, {'x': {'label': 'portable'}})
    write_definitions(b, {})
    apply(a, exchange(a, a_workspace))
    apply(b, exchange(b, b_workspace))
    write_definitions(b, {})
    apply(b, exchange(b, b_workspace))
    failure['offline'] = True
    assert exchange(a, a_workspace)['pending'] == 1
    failure['offline'] = False
    assert config_sync_retry(str(a_workspace), ENDPOINT, ACCOUNT)['pending'] == 0
    assert store.get(ACCOUNT).entries('scripts') == {}
    assert store.get(ACCOUNT).sections['scripts']['x']['deleted'] is True


def test_unsent_intent_is_not_dispatched_without_fresh_merge(tmp_path):
    from je_auto_control.utils.config_sync.outbox import SyncOperation, SyncOutbox
    box = SyncOutbox(tmp_path / 'outbox.sqlite', endpoint=ENDPOINT, user_id=ACCOUNT)
    try:
        box.enqueue_intent(SyncOperation(ENDPOINT, ACCOUNT, 'unsent', 0, ConfigBucket(ACCOUNT).to_dict()))
        report = box.drain(lambda _operation: pytest.fail('intent must first be merged'), now=1000)
        assert report.sent == 0 and report.pending == 1
    finally:
        box.close()


def test_atomic_rebase_refuses_to_replace_uncertain_envelopes(tmp_path):
    from je_auto_control.utils.config_sync.outbox import SyncOperation, SyncOutbox
    box = SyncOutbox(tmp_path / 'outbox.sqlite', endpoint=ENDPOINT, user_id=ACCOUNT)
    original = SyncOperation(ENDPOINT, ACCOUNT, 'uncertain', 0, ConfigBucket(ACCOUNT).to_dict())
    replacement = SyncOperation(ENDPOINT, ACCOUNT, 'replacement', 1, ConfigBucket(ACCOUNT).to_dict())
    try:
        box.enqueue(original)
        with pytest.raises(ConfigSyncError, match='uncertain'):
            box.enqueue(replacement, superseded=('uncertain',))
        assert [operation.envelope() for operation in box.pending()] == [original.envelope()]
    finally:
        box.close()


def test_preview_and_precancelled_exchange_do_not_queue_intent(tmp_path, sync_store):
    from threading import Event
    from je_auto_control.utils.config_sync.service import config_sync_preview, config_sync_status
    _store, failure = sync_store
    path, workspace = tmp_path / 'definitions.json', tmp_path / 'workspace'
    write_definitions(path, {'x': {'label': 'portable'}})
    failure['offline'] = True
    preview = config_sync_preview(str(path), str(workspace), ENDPOINT, ACCOUNT)
    assert preview['pending'] == 0
    cancelled = Event()
    cancelled.set()
    result = config_sync_exchange(str(path), str(workspace), ENDPOINT, ACCOUNT, cancel=cancelled)
    assert result['cancelled'] and config_sync_status(str(workspace), ENDPOINT, ACCOUNT)['pending'] == 0


def test_partial_apply_does_not_acknowledge_missing_assets(tmp_path, sync_store):
    import hashlib
    from je_auto_control.utils.config_sync.service import config_sync_status
    path, workspace = tmp_path / 'definitions.json', tmp_path / 'workspace'
    write_definitions(path, {})
    remote = ConfigBucket(ACCOUNT)
    causal_upsert(remote, 'scripts', 'x', {'label': 'portable', 'assets': [
        {'path': 'missing.png', 'size': 1, 'sha256': hashlib.sha256(b'x').hexdigest()}]}, device_id='remote')
    sync_store[0].commit(ACCOUNT, remote, base_revision=0, operation_id='seed')
    preview = exchange(path, workspace)
    assert apply(path, preview)['unresolved'] == ['scripts/x']
    assert config_sync_status(str(workspace), ENDPOINT, ACCOUNT)['applied_revision'] == 0


def test_remote_privacy_is_revalidated_before_rebase_persistence(tmp_path, sync_store, monkeypatch):
    path, workspace = tmp_path / 'definitions.json', tmp_path / 'workspace'
    write_definitions(path, {'x': {'label': 'portable'}})
    request = ConfigSyncClient._request
    calls = []

    def changed_remote(client, method, *, body=None):
        calls.append(method)
        if method == 'GET' and len(calls) >= 2:
            unsafe = ConfigBucket(ACCOUNT, {'scripts': {'leak': {'password': 'private-race-literal'}}})
            return {**unsafe.to_dict(), 'schema_version': 2, 'cas_supported': True}
        return request(client, method, body=body)

    monkeypatch.setattr(ConfigSyncClient, '_request', changed_remote)
    with pytest.raises(ConfigSyncError, match='confidential'):
        exchange(path, workspace)
    assert 'PUT' not in calls
    assert not list(workspace.rglob('preview.json'))
    for database in workspace.rglob('outbox.sqlite'):
        assert b'private-race-literal' not in database.read_bytes()


def test_modern_clipboard_keeps_event_identity_for_repeated_content():
    sender, receiver = ClipboardLoopGuard(origin='sender'), ClipboardLoopGuard(origin='receiver')
    first, second = sender.encode_text('A'), sender.encode_text('A')
    assert receiver.receive(first) == ('text', 'A')
    assert receiver.receive(second) == ('text', 'A')
    assert receiver.receive(first) is None
