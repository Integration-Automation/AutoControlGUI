"""Private-account cleanup is atomic and never deletes another account's same-address bytes."""
from hashlib import sha256
import sqlite3

import pytest

from je_auto_control.utils.config_sync.blob_models import SyncAssetBlob
from je_auto_control.utils.config_sync.blob_store import SyncAssetStore
from je_auto_control.utils.config_sync.contract import ConfigStoreError, ConfigSyncError


def publish(store, account, body):
    digest = sha256(body).hexdigest()
    blob = SyncAssetBlob(digest, len(body), (digest,) if body else ())
    if body:
        store.put_chunk(account, digest, body)
    store.commit(account, blob)
    return blob


def test_delete_one_private_account_preserves_same_digest_and_unpublished_other_account(tmp_path):
    path = tmp_path / 'blobs.sqlite3'
    store = SyncAssetStore(path)
    blob = publish(store, 'owned-transfer', b'shared-content')
    publish(store, 'unrelated', b'shared-content')
    extra = b'unpublished'
    store.put_chunk('unrelated', sha256(extra).hexdigest(), extra)
    assert store.delete_account('owned-transfer') == {'bytes': 14, 'chunks': 1, 'blobs': 1}
    assert store.status('owned-transfer') == {'bytes': 0, 'chunks': 0, 'blobs': 0}
    assert not store.contains('owned-transfer', blob)
    with SyncAssetStore(path).open('unrelated', blob) as stream:
        assert stream.read() == b'shared-content'
    assert store.read_chunk('unrelated', sha256(extra).hexdigest()) == extra
    assert store.delete_account('owned-transfer') == {'bytes': 0, 'chunks': 0, 'blobs': 0}
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT user_id FROM sync_asset_users').fetchall() == [('unrelated',)]


def test_empty_blob_account_cleanup_releases_account_capacity(tmp_path):
    store = SyncAssetStore(tmp_path / 'blobs.sqlite3', max_users=1)
    publish(store, 'expired-transfer', b'')
    assert store.delete_account('expired-transfer') == {'bytes': 0, 'chunks': 0, 'blobs': 1}
    assert publish(store, 'next-transfer', b'new')
    assert store.status('next-transfer') == {'bytes': 3, 'chunks': 1, 'blobs': 1}


def test_late_delete_failure_rolls_back_all_account_rows(tmp_path):
    path = tmp_path / 'blobs.sqlite3'
    store = SyncAssetStore(path)
    blob = publish(store, 'owned-transfer', b'original')
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON sync_asset_users "
                           "BEGIN SELECT RAISE(ABORT,'controlled late cleanup failure'); END")
    with pytest.raises(ConfigStoreError):
        store.delete_account('owned-transfer')
    assert SyncAssetStore(path).status('owned-transfer') == {'bytes': 8, 'chunks': 1, 'blobs': 1}
    with store.open('owned-transfer', blob) as stream:
        assert stream.read() == b'original'


def test_owned_orphan_chunks_are_removed_without_relying_on_account_counter(tmp_path):
    path = tmp_path / 'blobs.sqlite3'
    store = SyncAssetStore(path)
    store.status('initialize')
    body = b'orphan'
    with sqlite3.connect(path) as connection:
        connection.execute('INSERT INTO sync_asset_chunks VALUES (?,?,?)',
                           ('owned-transfer', sha256(body).hexdigest(), body))
    assert store.delete_account('owned-transfer') == {'bytes': 6, 'chunks': 1, 'blobs': 0}
    assert store.status('owned-transfer') == {'bytes': 0, 'chunks': 0, 'blobs': 0}


@pytest.mark.parametrize('account', [None, True, '', 'x' * 129])
def test_invalid_account_is_rejected_before_creating_a_database(tmp_path, account):
    path = tmp_path / 'must-not-exist.sqlite3'
    with pytest.raises(ConfigSyncError):
        SyncAssetStore(path).delete_account(account)
    assert not path.exists()
