"""Cold persisted transfer maintenance retains ownership through construction and rejects redirected cache paths."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from headless.test_agent_transfer_source import completed_source, create_for, review_for
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, transfer_records, transfer_source
from je_auto_control.utils.agent_runtime.file_target import FileTarget
from je_auto_control.utils.agent_runtime.transfer_protocol import AgentTransfers


def test_cold_maintenance_cannot_release_runtime_ownership_during_controller_construction(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        exported = create_for(runtime, review_for(runtime, task))
        clock = SimpleNamespace(time=lambda: exported['manifest']['expires'] + 1)
        monkeypatch.setattr(transfer_source, 'time', clock)
        monkeypatch.setattr(transfer_records, 'time', clock)
        runtime.close()
        reopened = AgentRuntime(runtime.store.path, targets={'local-files': FileTarget()})
        entered, release = Event(), Event()
        original = AgentTransfers.__init__
        def constructing(controller, *args, **kwargs):
            entered.set()
            assert release.wait(10)
            original(controller, *args, **kwargs)
        monkeypatch.setattr(AgentTransfers, '__init__', constructing)
        with closing(reopened), ThreadPoolExecutor(max_workers=1) as workers:
            maintaining = workers.submit(reopened.maintain)
            try:
                assert entered.wait(5)
                with pytest.raises(AgentTaskError, match='construction|mutation|active'):
                    reopened.close()
                with pytest.raises(AgentTaskError, match='still owns'):
                    AgentRuntime(reopened.store.path, targets={'local-files': FileTarget()})
            finally:
                release.set()
            maintaining.result(timeout=5)


def test_close_rechecks_a_controller_created_after_its_initial_retirement_check(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        exported = create_for(runtime, review_for(runtime, task))
        clock = SimpleNamespace(time=lambda: exported['manifest']['expires'] + 1)
        monkeypatch.setattr(transfer_source, 'time', clock)
        monkeypatch.setattr(transfer_records, 'time', clock)
        runtime.close()
        reopened = AgentRuntime(runtime.store.path, targets={'local-files': FileTarget()})
        close_entered, close_release, cleanup_entered, cleanup_release = (Event() for _ in range(4))
        original_close, original_delete = reopened._retained_browsers.close, PrivateTransferCache.delete_account
        def paused_close():
            close_entered.set()
            assert close_release.wait(10)
            original_close()
        def cleaning(cache, account):
            cleanup_entered.set()
            assert cleanup_release.wait(10)
            return original_delete(cache, account)
        monkeypatch.setattr(reopened._retained_browsers, 'close', paused_close)
        monkeypatch.setattr(PrivateTransferCache, 'delete_account', cleaning)
        with closing(reopened), ThreadPoolExecutor(max_workers=2) as workers:
            retiring = workers.submit(reopened.close)
            try:
                assert close_entered.wait(5)
                maintaining = workers.submit(reopened.maintain)
                assert cleanup_entered.wait(5)
                close_release.set()
                with pytest.raises(AgentTaskError, match='active transfer'):
                    retiring.result(timeout=5)
                with pytest.raises(AgentTaskError, match='still owns'):
                    AgentRuntime(reopened.store.path, targets={'local-files': FileTarget()})
            finally:
                close_release.set()
                cleanup_release.set()
            maintaining.result(timeout=5)


def test_cold_cleanup_rejects_redirected_cache_before_opening_storage_and_preserves_capacity(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache, private_cache_path
    from je_auto_control.utils.config_sync.database import SyncDatabase
    with completed_source(tmp_path) as (runtime, task, output, body, _users):
        exported = create_for(runtime, review_for(runtime, task))
        with runtime.store.connection() as connection:
            record = runtime.transfers.source.records.find(connection, exported['export_id'])
        clock = SimpleNamespace(time=lambda: record['expires'] + 1)
        monkeypatch.setattr(transfer_source, 'time', clock)
        monkeypatch.setattr(transfer_records, 'time', clock)
        cache_path = private_cache_path(runtime.store.path)
        assert cache_path.resolve().is_relative_to(tmp_path.resolve())
        backup = cache_path.with_name('preserved-owned-cache.sqlite3')
        assert backup.resolve().is_relative_to(tmp_path.resolve())
        runtime.close()
        cache_path.rename(backup)
        foreign_root = tmp_path / 'foreign-cache'
        foreign = PrivateTransferCache(foreign_root / 'unrelated.sqlite3')
        foreign_body = b'preserve unrelated cache with colliding account'
        digest = sha256(foreign_body).hexdigest()
        foreign.store.put_chunk(record['account'], digest, foreign_body)
        before = foreign.path.read_bytes()
        _junction(cache_path, foreign_root)
        original = SyncDatabase.connection
        def confined(database):
            if database._configured is not None and Path(database._configured) == cache_path:
                pytest.fail('a redirected private cache must be refused before its first storage connection')
            return original(database)
        monkeypatch.setattr(SyncDatabase, 'connection', confined)
        reopened = AgentRuntime(runtime.store.path, targets={'local-files': FileTarget()})
        try:
            with pytest.raises(AgentTaskError, match='cache path changed'):
                reopened.maintain()
            with reopened.store.connection() as connection:
                retained = reopened.transfers.source.records.find(connection, record['id'])
            assert retained['state'] == 'revoked' and retained['held'] is True
            assert retained['expires'] == record['expires']
            assert foreign.path.read_bytes() == before
            assert foreign.store.read_chunk(record['account'], digest) == foreign_body
            assert output.read_bytes() == body
        finally:
            assert cache_path.resolve() == foreign_root.resolve()
            cache_path.rmdir() if os.name == 'nt' else cache_path.unlink()
            backup.rename(cache_path)
            reopened.close()


def _junction(path, target):
    if os.name == 'nt':
        from _winapi import CreateJunction
        CreateJunction(str(target), str(path))
    else:
        path.symlink_to(target, target_is_directory=True)


def test_redirected_cache_parent_cannot_delete_a_foreign_valid_database_account(tmp_path):
    from uuid import uuid4
    from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
    owned_root, foreign_root = tmp_path / 'owned', tmp_path / 'foreign'
    cache = PrivateTransferCache(owned_root / 'runtime.sqlite3')
    foreign = PrivateTransferCache(foreign_root / 'runtime.sqlite3')
    account = uuid4().hex
    owned_body, foreign_body = b'original private account', b'preserve foreign private account'
    cache.store.put_chunk(account, sha256(owned_body).hexdigest(), owned_body)
    foreign.store.put_chunk(account, sha256(foreign_body).hexdigest(), foreign_body)
    before = foreign.path.read_bytes()
    backup = tmp_path / 'preserved-owned'
    assert owned_root.resolve().is_relative_to(tmp_path.resolve())
    assert backup.resolve().is_relative_to(tmp_path.resolve())
    owned_root.rename(backup)
    _junction(owned_root, foreign_root)
    try:
        with pytest.raises(AgentTaskError, match='cache path changed'):
            cache.delete_account(account)
        assert foreign.path.read_bytes() == before
        assert foreign.store.read_chunk(account, sha256(foreign_body).hexdigest()) == foreign_body
    finally:
        assert owned_root.resolve() == foreign_root.resolve()
        owned_root.rmdir() if os.name == 'nt' else owned_root.unlink()
        backup.rename(owned_root)
    assert cache.store.read_chunk(account, sha256(owned_body).hexdigest()) == owned_body
