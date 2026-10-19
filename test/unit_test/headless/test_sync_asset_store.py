"""Content-addressed chunks remain restart-safe, isolated and unpublished until a complete verified blob commits."""
from hashlib import sha256
import sqlite3

import pytest

import je_auto_control as ac

CHUNK = 256 * 1024


def descriptor(body):
    chunks = tuple(sha256(body[index:index + CHUNK]).hexdigest() for index in range(0, len(body), CHUNK))
    return ac.SyncAssetBlob(sha256(body).hexdigest(), len(body), chunks)


def test_blob_publication_requires_every_verified_chunk_and_survives_restart(tmp_path):
    path = tmp_path / 'assets.sqlite3'
    store = ac.SyncAssetStore(path)
    assert not path.exists()
    body = b'a' * CHUNK + b'last-chunk'
    blob = descriptor(body)
    assert store.missing_chunks('alice', blob) == blob.chunks
    assert store.put_chunk('alice', blob.chunks[0], body[:CHUNK]) is True
    assert store.put_chunk('alice', blob.chunks[0], body[:CHUNK]) is False
    with pytest.raises(ac.ConfigSyncError, match='missing'):
        store.commit('alice', blob)
    assert not store.contains('alice', blob)
    resumed = ac.SyncAssetStore(path)
    assert resumed.missing_chunks('alice', blob) == (blob.chunks[1],)
    resumed.put_chunk('alice', blob.chunks[1], body[CHUNK:])
    assert resumed.commit('alice', blob) is True
    assert resumed.commit('alice', blob) is False
    assert not resumed.contains('bob', blob)
    with ac.SyncAssetStore(path).open('alice', blob) as stream:
        assert stream.read() == body


def test_bad_chunk_or_whole_hash_never_publishes_or_poison_valid_content(tmp_path):
    store = ac.SyncAssetStore(tmp_path / 'assets.sqlite3')
    blob = descriptor(b'correct')
    with pytest.raises(ac.ConfigSyncError, match='hash'):
        store.put_chunk('alice', blob.chunks[0], b'damaged')
    assert store.missing_chunks('alice', blob) == blob.chunks
    store.put_chunk('alice', blob.chunks[0], b'correct')
    wrong = ac.SyncAssetBlob('f' * 64, blob.size, blob.chunks)
    with pytest.raises(ac.ConfigSyncError, match='hash'):
        store.commit('alice', wrong)
    assert not store.contains('alice', wrong)
    assert store.commit('alice', blob)


def test_asset_quotas_count_unique_account_chunks_and_roll_back_refused_new_users(tmp_path):
    store = ac.SyncAssetStore(tmp_path / 'assets.sqlite3', max_users=1, max_bytes=4)
    one, two = descriptor(b'abcd'), descriptor(b'ef')
    store.put_chunk('alice', one.chunks[0], b'abcd')
    assert not store.put_chunk('alice', one.chunks[0], b'abcd')
    with pytest.raises(ac.ConfigStoreFull):
        store.put_chunk('alice', two.chunks[0], b'ef')
    with pytest.raises(ac.ConfigStoreFull):
        store.put_chunk('bob', two.chunks[0], b'ef')
    assert store.status('alice') == {'bytes': 4, 'chunks': 1, 'blobs': 0}
    assert store.status('bob') == {'bytes': 0, 'chunks': 0, 'blobs': 0}


def test_blob_read_refuses_tampered_chunk_without_returning_unverified_bytes(tmp_path):
    path = tmp_path / 'assets.sqlite3'
    store = ac.SyncAssetStore(path)
    blob = descriptor(b'correct')
    store.put_chunk('alice', blob.chunks[0], b'correct')
    store.commit('alice', blob)
    with sqlite3.connect(path) as connection:
        connection.execute('UPDATE sync_asset_chunks SET body=?', (b'damaged',))
    with pytest.raises(ac.ConfigStoreError, match='integrity'):
        store.open('alice', blob)


def test_empty_blobs_and_portable_asset_references_have_exact_bounded_wire(tmp_path):
    blob = descriptor(b'')
    store = ac.SyncAssetStore(tmp_path / 'assets.sqlite3')
    assert store.commit('alice', blob)
    with store.open('alice', blob) as stream:
        assert stream.read() == b''
    reference = ac.SyncAssetReference('assets/templates/button.png', blob)
    assert ac.SyncAssetReference.from_dict(reference.to_dict()) == reference
    assert reference.file == ac.AssetFile('assets/templates/button.png', blob.sha256, 0)
    with pytest.raises(ac.ConfigSyncError):
        ac.SyncAssetReference('../private', blob)
    with pytest.raises(ac.ConfigSyncError):
        ac.SyncAssetReference('profile/settings.json', blob)
    with pytest.raises(ac.ConfigSyncError):
        ac.SyncAssetBlob(blob.sha256, 1, ())


def test_late_blob_receipt_failure_leaves_verified_chunks_for_exact_retry(tmp_path):
    path = tmp_path / 'assets.sqlite3'
    store = ac.SyncAssetStore(path)
    blob = descriptor(b'durable')
    store.put_chunk('alice', blob.chunks[0], b'durable')
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER fail_blob BEFORE INSERT ON sync_asset_blobs "
                           "BEGIN SELECT RAISE(ABORT,'controlled late failure'); END")
    with pytest.raises(ac.ConfigStoreError):
        store.commit('alice', blob)
    assert not store.contains('alice', blob) and not store.missing_chunks('alice', blob)
    with sqlite3.connect(path) as connection:
        connection.execute('DROP TRIGGER fail_blob')
    assert ac.SyncAssetStore(path).commit('alice', blob)


def test_asset_object_count_quotas_bound_chunk_and_manifest_growth(tmp_path):
    store = ac.SyncAssetStore(tmp_path / 'assets.sqlite3', max_chunks=1, max_blobs=1)
    body = b'a' * CHUNK
    one, two = descriptor(body), descriptor(body * 2)
    store.put_chunk('alice', one.chunks[0], body)
    store.commit('alice', one)
    with pytest.raises(ac.ConfigStoreFull):
        store.put_chunk('alice', sha256(b'new').hexdigest(), b'new')
    with pytest.raises(ac.ConfigStoreFull):
        store.commit('alice', two)
    assert not store.put_chunk('alice', one.chunks[0], body)
    assert not store.commit('alice', one)
    assert store.status('alice') == {'bytes': CHUNK, 'chunks': 1, 'blobs': 1}


@pytest.mark.parametrize('future', [False, True])
def test_foreign_or_future_asset_database_is_never_modified(tmp_path, future):
    from je_auto_control.utils.config_sync.blob_schema import _APPLICATION
    path = tmp_path / 'foreign.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE important (value TEXT)')
        connection.execute("INSERT INTO important VALUES ('preserve')")
        if future:
            connection.execute(f'PRAGMA application_id={_APPLICATION}')
            connection.execute('PRAGMA user_version=2')
    with pytest.raises(ac.ConfigStoreError):
        ac.SyncAssetStore(path).status('alice')
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT value FROM important').fetchone()[0] == 'preserve'
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [('important',)]
