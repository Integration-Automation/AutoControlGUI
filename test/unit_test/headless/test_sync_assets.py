"""Content-addressed asset generations publish complete verified bundles without executing their scripts."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
import json
from threading import Event

import pytest

import je_auto_control as ac


def asset_bundle(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'templates').mkdir()
    (source / 'templates' / 'button.png').write_bytes(b'controlled-template')
    (source / 'script.json').write_text(json.dumps([['AC_locate', {'template': 'templates/button.png'}]]),
                                       encoding='utf-8')
    manifest = ac.build_asset_manifest(source, ['script.json', 'templates/button.png'])
    return source, manifest, ac.DirectoryAssetTransport(source, tmp_path / 'received')


def test_script_asset_hash_round_trip_publishes_one_complete_generation(tmp_path, monkeypatch):
    source, manifest, transport = asset_bundle(tmp_path)
    monkeypatch.setattr(ac.executor, 'execute_action', lambda *args, **kwargs: pytest.fail('sync executed a script'))
    assert 'source' not in json.dumps(manifest.to_dict())
    assert ac.AssetManifest.from_dict(manifest.to_dict()) == manifest
    result = ac.sync_assets(manifest, transport)
    for item in manifest.files:
        assert (result.directory / item.path).read_bytes() == (source / item.path).read_bytes()
        assert sha256((result.directory / item.path).read_bytes()).hexdigest() == item.sha256
    repeated = ac.sync_assets(manifest, transport)
    assert repeated.directory == result.directory and repeated.reused is True


def test_late_hash_failure_publishes_no_partial_script_or_template(tmp_path):
    source, manifest, transport = asset_bundle(tmp_path)
    (source / 'templates' / 'button.png').write_bytes(b'corrupt-template')
    with pytest.raises(ac.ConfigSyncError):
        ac.sync_assets(manifest, transport)
    assert not list((tmp_path / 'received').glob('generation-*'))
    assert not list((tmp_path / 'received').glob('.incoming-*'))


def test_cancelled_asset_read_keeps_previous_complete_generation_and_cleans_staging(tmp_path):
    _source, manifest, transport = asset_bundle(tmp_path)
    previous = ac.sync_assets(manifest, transport)
    changed = ac.AssetManifest((ac.AssetFile('next.json', sha256(b'next').hexdigest(), 4),))
    event = Event()
    class CancelledTransport:
        target_root = transport.target_root
        def open(self, _asset):
            event.set()
            return BytesIO(b'next')
    with pytest.raises(CancelledError):
        ac.sync_assets(changed, CancelledTransport(), cancelled=event.is_set)
    assert (previous.directory / 'script.json').is_file()
    assert len(list(transport.target_root.glob('generation-*'))) == 1
    assert not list(transport.target_root.glob('.incoming-*'))


@pytest.mark.parametrize('path', ['../outside', '/absolute', 'C:/drive', 'folder\\file',
                                 'folder/../file', 'NUL.txt', 'file:stream', 'file.', 'file '])
def test_asset_manifest_refuses_nonportable_paths_before_any_storage(path):
    with pytest.raises(ac.ConfigSyncError):
        ac.AssetFile(path, '0' * 64, 1)


def test_asset_manifest_refuses_case_aliases_and_file_directory_collisions():
    for paths in [('A.json', 'a.json'), ('a', 'a/b'), ('Templates/a.png', 'templates/b.png'),
                  ('Templates/a', 'unrelated/x', 'templates/b'), ('caf\u00e9/a', 'cafe\u0301/b')]:
        with pytest.raises(ac.ConfigSyncError):
            ac.AssetManifest(tuple(ac.AssetFile(path, '0' * 64, 1) for path in paths))


def test_tampered_cached_generation_is_refused_without_overwriting_evidence(tmp_path):
    _source, manifest, transport = asset_bundle(tmp_path)
    result = ac.sync_assets(manifest, transport)
    script = result.directory / 'script.json'
    script.write_bytes(b'tampered')
    with pytest.raises(ac.ConfigSyncError):
        ac.sync_assets(manifest, transport)
    assert script.read_bytes() == b'tampered'


def test_cached_generation_rejects_unmanifested_files(tmp_path):
    _source, manifest, transport = asset_bundle(tmp_path)
    result = ac.sync_assets(manifest, transport)
    extra = result.directory / 'unexpected-script.json'
    extra.write_text('[]', encoding='utf-8')
    with pytest.raises(ac.ConfigSyncError):
        ac.sync_assets(manifest, transport)
    assert extra.is_file()


def test_asset_source_symbolic_link_cannot_read_outside_its_root(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    outside = tmp_path / 'private.txt'
    outside.write_text('local-only', encoding='utf-8')
    try:
        (source / 'asset.txt').symlink_to(outside)
    except OSError:
        pytest.skip('symbolic link creation is unavailable')
    with pytest.raises(ac.ConfigSyncError):
        ac.build_asset_manifest(source, ['asset.txt'])


def test_asset_transport_creation_is_lazy_and_precancel_makes_no_target_directory(tmp_path):
    transport = ac.DirectoryAssetTransport(tmp_path / 'missing-source', tmp_path / 'missing-target')
    manifest = ac.AssetManifest((ac.AssetFile('script.json', '0' * 64, 1),))
    with pytest.raises(CancelledError):
        ac.sync_assets(manifest, transport, cancelled=lambda: True)
    assert not transport.target_root.exists()


def test_parallel_asset_transfers_publish_only_one_complete_generation(tmp_path):
    _source, manifest, transport = asset_bundle(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _index: ac.sync_assets(manifest, transport), range(8)))
    assert len({result.directory for result in results}) == 1
    assert len(list(transport.target_root.glob('generation-*'))) == 1
    assert not list(transport.target_root.glob('.incoming-*'))
    assert ac.sync_assets(manifest, transport).reused


def test_empty_assets_are_verified_and_oversize_streams_publish_nothing(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'empty.json').write_bytes(b'')
    manifest = ac.build_asset_manifest(source, ['empty.json'])
    transport = ac.DirectoryAssetTransport(source, tmp_path / 'target')
    assert (ac.sync_assets(manifest, transport).directory / 'empty.json').read_bytes() == b''
    (source / 'empty.json').write_bytes(b'extra')
    with pytest.raises(ac.ConfigSyncError):
        ac.sync_assets(manifest, ac.DirectoryAssetTransport(source, tmp_path / 'other-target'))
    assert not list((tmp_path / 'other-target').glob('generation-*'))


@pytest.mark.parametrize('error_type', [OSError, ac.ConfigSyncError])
def test_wrapped_transport_cancellation_keeps_its_control_flow_signal(tmp_path, error_type):
    class InterruptedTransport:
        target_root = tmp_path / 'target'
        def open(self, _asset):
            raise error_type('wrapped interrupted transfer') from CancelledError()
    manifest = ac.AssetManifest((ac.AssetFile('script.json', '0' * 64, 1),))
    with pytest.raises(CancelledError):
        ac.sync_assets(manifest, InterruptedTransport())
    assert not list(InterruptedTransport.target_root.glob('generation-*'))
