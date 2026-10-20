"""Retired folder baselines move to a new sender without filesystem reads, shared mutation or overlapping workers."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
import os
from threading import Event

import pytest

from headless.test_folder_sync_content import loop
from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncCheckpoint, FolderSyncEngine, FolderSyncStateError


def test_checkpoint_retains_baseline_failed_sends_and_receipts_without_reading_the_watch(tmp_path, monkeypatch):
    existing = tmp_path / 'existing.bin'
    existing.write_bytes(b'initial')

    def failed(*_args):
        raise OSError('connection lost')

    old = FolderSyncEngine(watch_dir=tmp_path, sender=failed)
    loop(old, lambda: (tmp_path / 'pending.bin').write_bytes(b'pending'))
    received = tmp_path / 'received.bin'
    received.write_bytes(b'received bytes')
    assert old.record_receipt(FileReceiveReceipt(received, sha256(b'received bytes').hexdigest(), 14))
    old.stop()
    with monkeypatch.context() as guard:
        guard.setattr(Path, 'stat', lambda *_args, **_kwargs: pytest.fail('checkpoint accessed the filesystem'))
        checkpoint = old.checkpoint()
        replacement = FolderSyncEngine(watch_dir=tmp_path, sender=lambda *_args: None, checkpoint=checkpoint)
    assert checkpoint.baselined and dict(checkpoint.entries) == old._content.snapshot
    assert 'pending.bin' not in dict(checkpoint.entries)
    existing.write_bytes(b'offline edit')
    sent = []
    replacement._sender = lambda path, name: sent.append((name, Path(path).read_bytes()))
    loop(replacement)
    assert sorted(sent) == [('existing.bin', b'offline edit'), ('pending.bin', b'pending')]
    assert replacement._content.snapshot['existing.bin'] == sha256(b'offline edit').hexdigest()
    assert dict(checkpoint.entries)['existing.bin'] == sha256(b'initial').hexdigest()
    assert old._content.snapshot['existing.bin'] == sha256(b'initial').hexdigest()
    with pytest.raises(FrozenInstanceError):
        checkpoint.baselined = False


def test_checkpoint_requires_explicit_stop_and_actual_worker_exit(tmp_path):
    entered, release = Event(), Event()

    def blocked(*_args):
        entered.set()
        assert release.wait(10)

    engine = FolderSyncEngine(watch_dir=tmp_path, sender=blocked, poll_interval_s=.5)
    with pytest.raises(FolderSyncStateError, match='retired'):
        engine.checkpoint()
    engine.start()
    assert engine.wait_until_ready()
    (tmp_path / 'pending.bin').write_bytes(b'pending')
    try:
        assert entered.wait(5)
        worker = engine._thread
        engine.stop()
        assert engine.is_running() and engine.stop_requested
        with pytest.raises(FolderSyncStateError, match='retired'):
            engine.checkpoint()
    finally:
        release.set()
        engine.stop()
    assert worker is not None and not worker.is_alive()
    assert 'pending.bin' in dict(engine.checkpoint().entries)


@pytest.mark.parametrize('mismatch', ['path', 'recursion', 'object'])
def test_checkpoint_cannot_change_the_watch_root_or_recursion_mode(tmp_path, mismatch):
    original = FolderSyncEngine(watch_dir=tmp_path, sender=lambda *_args: None)
    original.stop()
    checkpoint = original.checkpoint()
    options = {'watch_dir': tmp_path, 'sender': lambda *_args: None, 'checkpoint': checkpoint}
    if mismatch == 'path':
        options['watch_dir'] = tmp_path / 'other'
    elif mismatch == 'recursion':
        options['include_subdirs'] = True
    else:
        options['checkpoint'] = object()
    with pytest.raises(FolderSyncStateError, match='does not match'):
        FolderSyncEngine(**options)


@pytest.mark.parametrize('changes', [
    {'watch_dir': Path('relative')}, {'watch_dir': '/unbound/string'},
    {'include_subdirs': 1}, {'baselined': 1}, {'entries': []},
    {'entries': (('file.bin', 'x' * 64),)}, {'entries': (('file.bin', 'A' * 64),)},
    {'entries': (('file.bin', b'a' * 64),)}, {'entries': (['file.bin', 'a' * 64],)},
    {'entries': (('file.bin', 'a' * 64, 'extra'),)}, {'entries': ((5, 'a' * 64),)},
    {'entries': (('file.bin', 'a' * 64), ('file.bin', 'b' * 64))},
    {'entries': (('child/file.bin', 'a' * 64),)},
], ids=['relative-root', 'string-root', 'int-recursion', 'int-baselined', 'mutable-entries', 'bad-digest',
        'uppercase-digest', 'bytes-digest', 'mutable-entry', 'extra-field', 'nontext-path', 'duplicate',
        'excluded-child'])
def test_invalid_checkpoint_shapes_are_refused(tmp_path, changes):
    valid = FolderSyncCheckpoint(tmp_path, False, (), False)
    with pytest.raises(FolderSyncStateError):
        replace(valid, **changes)


@pytest.mark.parametrize('name', ['', '/absolute', '../outside', 'child/../outside', './file', 'child//file',
                               'child/', '.', 'bad\x00name', *(['C:/drive', r'child\file'] if os.name == 'nt' else [])])
def test_checkpoint_refuses_paths_outside_its_relative_namespace(tmp_path, name):
    with pytest.raises(FolderSyncStateError):
        FolderSyncCheckpoint(tmp_path, True, ((name, 'a' * 64),), True)


def test_checkpoint_preserves_native_names_that_are_not_drive_or_separator_syntax(tmp_path):
    names = ['normal.bin', '測試.bin'] if os.name == 'nt' else ['name:part.bin', r'literal\slash.bin']
    for name in names:
        (tmp_path / name).write_bytes(b'initial')
    old = FolderSyncEngine(watch_dir=tmp_path, sender=lambda *_args: None)
    loop(old)
    old.stop()
    checkpoint = old.checkpoint()
    assert set(dict(checkpoint.entries)) == set(names)
    sent = []
    new = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, name: sent.append(name), checkpoint=checkpoint)
    loop(new, lambda: (tmp_path / names[0]).write_bytes(b'changed'))
    assert sent == [names[0]]


def test_unbaselined_and_recursive_checkpoints_keep_their_original_initial_scan_semantics(tmp_path):
    child = tmp_path / 'child'
    child.mkdir()
    (child / 'received.bin').write_bytes(b'received')
    checkpoint = FolderSyncCheckpoint(tmp_path, True, (('child/received.bin', sha256(b'received').hexdigest()),), False)
    sent = []
    engine = FolderSyncEngine(watch_dir=tmp_path, include_subdirs=True,
                              sender=lambda path, name: sent.append(name), checkpoint=checkpoint)
    (tmp_path / 'preexisting.bin').write_bytes(b'ignored initial file')
    loop(engine, lambda: (child / 'new.bin').write_bytes(b'new'))
    assert sent == ['child/new.bin']
