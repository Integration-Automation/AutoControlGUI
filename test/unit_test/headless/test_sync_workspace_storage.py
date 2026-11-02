"""Storage migrations and late failures preserve causal source heads, queued wire and resync generation boundaries."""
import sqlite3

import pytest

import je_auto_control as ac
from je_auto_control.utils.config_sync.adapter_ledger import fingerprint

ENDPOINT = 'https://controlled.invalid'


def operation(name, value='dark'):
    entry = ac.SyncEntry('settings', 'theme', {'value': value}, {'desktop': 1}, name, 'desktop')
    return ac.SyncOperation(name, ENDPOINT, 'alice', 'desktop', (entry,))


def test_enqueue_many_rolls_back_a_late_sql_failure_without_partial_edits(tmp_path):
    path = tmp_path / 'outbox.sqlite3'
    queue = ac.SyncOutbox(path)
    queue.identity(ENDPOINT, 'alice', origin='desktop')
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER fail_second BEFORE INSERT ON sync_operations "
                           "WHEN NEW.operation_id='second' BEGIN SELECT RAISE(ABORT,'controlled failure'); END")
    with pytest.raises(ac.ConfigStoreError):
        queue.enqueue_many((operation('first'), operation('second')))
    assert queue.pending(endpoint=ENDPOINT, user_id='alice') == ()
    with sqlite3.connect(path) as connection:
        connection.execute('DROP TRIGGER fail_second')
    assert queue.enqueue_many((operation('first'), operation('second'))) == 2
    assert queue.enqueue_many((operation('first'), operation('second'))) == 0


def test_changed_late_batch_identity_cannot_insert_earlier_new_work(tmp_path):
    queue = ac.SyncOutbox(tmp_path / 'outbox.sqlite3')
    queue.enqueue(operation('existing'))
    with pytest.raises(ac.ConfigSyncError, match='different'):
        queue.enqueue_many((operation('new'), operation('existing', 'light')))
    assert queue.pending(endpoint=ENDPOINT, user_id='alice') == (operation('existing'),)


def test_outbox_version_two_upgrade_keeps_edit_cache_and_control_receipt_bytes(tmp_path):
    from je_auto_control.utils.config_sync.control_models import SyncControlOperation
    from je_auto_control.utils.config_sync.control_store import _logical
    path = tmp_path / 'outbox.sqlite3'
    queue = ac.SyncOutbox(path)
    item = operation('offline')
    queue.enqueue(item)
    identity = queue.identity(ENDPOINT, 'alice')
    snapshot = ac.CausalBucket('alice')
    queue.observe(snapshot, endpoint=ENDPOINT)
    control = SyncControlOperation('joined', identity, 'register')
    wire, digest = _logical(control)
    with sqlite3.connect(path) as connection:
        connection.execute('INSERT INTO sync_control_receipts VALUES (?,?,?,?,?,?)',
                           (ENDPOINT, 'alice', 'joined', wire, digest, 1))
        for name in ('sync_workspace_leases', 'sync_workspace_bindings', 'sync_workspace_baselines'):
            connection.execute(f'DROP TABLE {name}')
        connection.execute('PRAGMA user_version=2')
        before = connection.execute('SELECT wire,digest FROM sync_operations').fetchall()
        receipt = connection.execute('SELECT * FROM sync_control_receipts').fetchall()
    assert ac.SyncOutbox(path).pending(endpoint=ENDPOINT, user_id='alice') == (item,)
    assert ac.SyncOutbox(path).snapshot(endpoint=ENDPOINT, user_id='alice') == snapshot
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 3
        assert connection.execute('SELECT wire,digest FROM sync_operations').fetchall() == before
        assert connection.execute('SELECT * FROM sync_control_receipts').fetchall() == receipt


def test_adapter_version_one_upgrade_preserves_source_heads_and_receipts(tmp_path):
    from je_auto_control.utils.config_sync.adapter_state import _APPLICATION
    path = tmp_path / 'adapters.sqlite3'
    identity = ac.SyncLocalIdentity(ENDPOINT, 'alice', 'desktop')
    state = ac.SyncAdapterState(path, identity)
    original, _ = state.update('settings', {'theme': {'value': 'dark'}}, {})
    with sqlite3.connect(path) as connection:
        connection.execute('DROP TABLE adapter_adoptions')
        connection.execute('ALTER TABLE adapter_seen DROP COLUMN compacted')
        connection.execute('PRAGMA user_version=1')
        assert connection.execute('PRAGMA application_id').fetchone()[0] == _APPLICATION
        sources = connection.execute('SELECT * FROM adapter_sources').fetchall()
        seen = connection.execute('SELECT * FROM adapter_seen').fetchall()
    restored = ac.SyncAdapterState(path, identity)
    assert restored.heads('settings') == original
    assert restored.update('settings', {'theme': {'value': 'dark'}}, {})[0] == original
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        assert connection.execute('SELECT * FROM adapter_sources').fetchall() == sources
        assert connection.execute('SELECT scope,entry_id,origin,operation_id,change_id,digest '
                                  'FROM adapter_seen').fetchall() == seen


def test_repeated_adoption_never_replaces_new_work_in_an_adopted_generation(tmp_path):
    identity = ac.SyncLocalIdentity(ENDPOINT, 'alice', 'desktop', epoch=1)
    state = ac.SyncAdapterState(tmp_path / 'adapters.sqlite3', identity)
    baseline = {'theme': fingerprint({'value': 'dark'})}
    state.adopt('settings', {}, baseline, operation_id='reset')
    assert state.update('settings', {'theme': {'value': 'dark'}}, {})[0] == {}
    changed, _ = state.update('settings', {'theme': {'value': 'light'}}, {})
    state.adopt('settings', {}, baseline, operation_id='reset')
    assert state.heads('settings') == changed
    assert state.update('settings', {'theme': {'value': 'light'}}, {})[0] == changed


def test_compacted_fence_accepts_late_deleted_payload_without_accepting_live_equivocation(tmp_path):
    identity = ac.SyncLocalIdentity(ENDPOINT, 'alice', 'laptop')
    state = ac.SyncAdapterState(tmp_path / 'adapters.sqlite3', identity)
    deleted = ac.SyncEntry('settings', 'theme', {'value': 'dark'}, {'desktop': 2}, 'deleted', 'desktop', True)
    fence = ac.SyncEntry('settings', 'theme', {}, deleted.version, deleted.operation_id, deleted.origin, True)
    state.update('settings', None, {fence.change_id: fence}, compacted=frozenset({fence.change_id}))
    assert state.update('settings', None, {deleted.change_id: deleted})[0] == {fence.change_id: fence}
    live = ac.SyncEntry('settings', 'theme', {'value': 'dark'}, deleted.version, deleted.operation_id, deleted.origin)
    with pytest.raises(ac.ConfigSyncError):
        state.update('settings', None, {live.change_id: live})
    assert state.heads('settings') == {fence.change_id: fence}
