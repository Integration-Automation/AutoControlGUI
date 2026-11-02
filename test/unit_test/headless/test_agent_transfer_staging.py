"""Actual publication journals exact staging identities before bytes and never cleans unrelated user output."""
from pathlib import Path
from threading import Event
import time

import pytest

from headless.test_agent_transfer_import import import_hosts
from headless.test_agent_transfer_import_lifecycle import operation, review, wait_import
from je_auto_control.utils.agent_runtime import AgentTaskError


def test_staging_is_durably_owned_before_copy_and_cancel_cleans_only_that_stage(tmp_path, monkeypatch):
    from je_auto_control.utils.config_sync import assets
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, _actor):
        entered, release = Event(), Event()
        copied = []
        original = assets._copy_stream
        def paused(source, asset, path, cancelled, *args):
            copied.append(Path(path))
            entered.set()
            assert release.wait(10)
            return original(source, asset, path, cancelled, *args)
        monkeypatch.setattr(assets, '_copy_stream', paused)
        unrelated = root / 'user-journal.json'
        unrelated.write_bytes(b'unrelated user data')
        try:
            status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
            assert status == 200, reply
            identifier = reply['import']['import_id']
            assert entered.wait(5)
            with host.runtime.store.connection() as connection:
                delivery = host.runtime.transfers._life.importer._state.jobs.ledger.read(connection, identifier)
            publication = delivery['publication']
            assert 'staging' in publication, 'the real staging directory must be journaled before its first byte'
            witness = publication['staging']
            stage = Path(witness['path'])
            assert stage == copied[0].parent.parent
            assert witness['directories'][''] == [stage.stat().st_dev, stage.stat().st_ino]
            assert witness['files']['files/report.txt'] == [copied[0].stat().st_dev, copied[0].stat().st_ino]
            assert copied[0].stat().st_size == 0
            status, cancelled = operation(server, token, 'cancel_import', {'import_id': identifier})
            assert status == 200, cancelled
            release.set()
            deadline = time.monotonic() + 10
            while stage.exists():
                assert time.monotonic() < deadline, 'the fenced producer must retire its exact private staging'
                time.sleep(0.05)
            assert wait_import(server, token, identifier)['state'] == 'requires_review'
            assert unrelated.read_bytes() == b'unrelated user data'
            assert not list((root / 'received').rglob('generation-*'))
        finally:
            release.set()


@pytest.mark.parametrize('boundary', ['retry', 'restart', 'extra-file', 'replacement-directory'])
def test_expiry_retries_only_the_journaled_stage_after_producer_cleanup_failed(tmp_path, monkeypatch, boundary):
    from types import SimpleNamespace
    from headless.test_agent_transfer_import_restart import restart_destination
    from je_auto_control.utils.agent_runtime import transfer_import
    from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
    from je_auto_control.utils.config_sync import assets
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, actor):
        failed = []
        original_rmdir = Path.rmdir
        def abort_copy(*_args):
            raise AgentTaskError('owned failure before staging bytes')
        def failed_rmdir(path):
            if path.name.startswith('.incoming-') and path.parent.name.startswith('import-'):
                failed.append(path)
                raise OSError('owned staging retirement failure')
            return original_rmdir(path)
        with monkeypatch.context() as scoped:
            scoped.setattr(assets, '_copy_stream', abort_copy)
            scoped.setattr(Path, 'rmdir', failed_rmdir)
            status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
            assert status == 200, reply
            identifier = reply['import']['import_id']
            assert wait_import(server, token, identifier)['state'] == 'requires_review'
        assert len(failed) == 1
        stage = failed[0]
        assert stage.exists()
        jobs = host.runtime.transfers._life.importer._state.jobs
        deadline = time.monotonic() + 10
        while not jobs.retired(identifier):
            assert time.monotonic() < deadline
            time.sleep(0.05)
        with host.runtime.store.connection() as connection:
            record = host.runtime.transfers.source.records.find(connection, identifier)
        if boundary == 'replacement-directory':
            stage.rename(stage.with_name('preserved-original'))
            stage.mkdir()
        if boundary in {'extra-file', 'replacement-directory'}:
            unrelated = stage / 'user-journal.json'
            unrelated.write_bytes(b'preserve unrelated data')
        monkeypatch.setattr(transfer_import, 'time', SimpleNamespace(
            time=lambda: record['expires'] + 1, monotonic=time.monotonic))
        if boundary in {'extra-file', 'replacement-directory'}:
            with pytest.raises(AgentTaskError, match='identity|unrecognized'):
                host.runtime.transfers.maintain()
            assert unrelated.read_bytes() == b'preserve unrelated data'
            assert PrivateTransferCache(host.runtime.store.path).store.status(record['account'])['chunks'] > 0
            with host.runtime.store.connection() as connection:
                assert host.runtime.transfers.source.records.find(connection, identifier)['held'] is True
            return
        if boundary == 'restart':
            with restart_destination(host, server, actor) as (restarted, _named):
                restarted.runtime.transfers.maintain()
                with restarted.runtime.store.connection() as connection:
                    assert restarted.runtime.transfers.source.records.find(connection, identifier)['held'] is False
            assert not stage.exists()
            return
        host.runtime.transfers.maintain()
        assert not stage.exists(), 'expiry must retire the exact journaled stage before releasing its reservation'
        with host.runtime.store.connection() as connection:
            after = host.runtime.transfers.source.records.find(connection, identifier)
        assert after['held'] is False
        assert after['expires'] == record['expires']


@pytest.mark.parametrize('change', ['extra-file', 'replacement-directory'])
def test_staging_cleanup_refuses_unrecognized_or_replaced_objects(tmp_path, change):
    from hashlib import sha256
    from je_auto_control.utils.agent_runtime.transfer_staging import ImportStaging
    from je_auto_control.utils.config_sync.asset_models import AssetFile, AssetManifest
    root = tmp_path / 'owned-root'
    root.mkdir()
    status = root.stat()
    journal, retired = [], []
    staging = ImportStaging(root, [status.st_dev, status.st_ino], journal.append, retired.append)
    manifest = AssetManifest((AssetFile('report.txt', sha256(b'x').hexdigest(), 1),))
    with pytest.raises(AgentTaskError, match='identity|unrecognized'):
        with staging.directory(root, manifest) as directory:
            if change == 'replacement-directory':
                directory.rename(root / 'preserved-original')
                directory.mkdir()
            unexpected = directory / 'user-journal.json'
            unexpected.write_bytes(b'preserve unrelated data')
    assert unexpected.read_bytes() == b'preserve unrelated data'
    assert retired == []
    assert journal and journal[0]['cleaned'] is False


@pytest.mark.parametrize('cancelled', [False, True])
def test_shared_publisher_uses_journaled_nested_empty_and_multichunk_files(tmp_path, cancelled):
    from concurrent.futures import CancelledError
    from je_auto_control.utils.agent_runtime.transfer_staging import ImportStaging
    from je_auto_control.utils.config_sync.assets import _sync_assets, DirectoryAssetTransport, build_asset_manifest
    source, root = tmp_path / 'source', tmp_path / 'owned-root'
    source.mkdir()
    root.mkdir()
    (source / 'nested').mkdir()
    contents = {'nested/empty.txt': b'', 'nested/large.bin': b'chunk\x00' * 50000, 'report.txt': b'report'}
    for name, body in contents.items():
        (source / name).write_bytes(body)
    manifest = build_asset_manifest(source, contents)
    identity = root.stat()
    journal, retired = [], []
    staging = ImportStaging(root, [identity.st_dev, identity.st_ino], journal.append, retired.append)
    def check():
        return cancelled and bool(staging._state.used)
    if cancelled:
        with pytest.raises(CancelledError):
            _sync_assets(manifest, DirectoryAssetTransport(source, root), cancelled=check, staging=staging)
        assert list(root.iterdir()) == []
    else:
        result = _sync_assets(manifest, DirectoryAssetTransport(source, root), staging=staging)
        for name, body in contents.items():
            assert (result.directory / name).read_bytes() == body
    assert len(journal) == len(retired) == 1
    assert set(journal[0]['files']) == {'manifest.json', *('files/' + name for name in contents)}
    assert journal[0] == retired[0]
    assert not Path(journal[0]['path']).exists()
