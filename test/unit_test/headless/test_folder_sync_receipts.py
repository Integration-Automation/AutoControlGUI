"""Published receive receipts and failed scans preserve folder content ownership without native devices."""
from concurrent.futures import CancelledError
from pathlib import Path

import pytest

from headless.test_folder_sync_content import loop
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine


def test_received_bytes_do_not_echo_but_a_later_local_edit_is_sent(tmp_path):
    target = tmp_path / 'received.txt'
    sent = []
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, name: sent.append(Path(path).read_bytes()))

    def received():
        target.write_bytes(b'remote content')
        assert engine.record_received(target)

    loop(engine, received, lambda: target.write_bytes(b'local edit'), lambda: None)
    assert sent == [b'local edit']


def test_newer_receive_receipt_wins_over_an_older_send_completion(tmp_path):
    target = tmp_path / 'shared.txt'
    sent = []

    def send(path, _name):
        sent.append(Path(path).read_bytes())
        target.write_bytes(b'newer remote')
        assert engine.record_received(target)

    engine = FolderSyncEngine(watch_dir=tmp_path, sender=send)
    loop(engine, lambda: target.write_bytes(b'old local'), lambda: None)
    assert sent == [b'old local'] and target.read_bytes() == b'newer remote'


def test_receive_during_initial_scan_is_not_overwritten_by_the_older_baseline(tmp_path, monkeypatch):
    target = tmp_path / 'shared.txt'
    target.write_bytes(b'original')
    sent = []
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, name: sent.append(name))
    scan = engine._scan
    first = True

    def received_during_scan(stop):
        nonlocal first
        result = scan(stop)
        if first:
            first = False
            target.write_bytes(b'remote update')
            assert engine.record_received(target)
        return result

    monkeypatch.setattr(engine, '_scan', received_during_scan)
    loop(engine, lambda: None)
    assert sent == []


def test_receive_after_scan_is_not_pruned_as_a_deleted_file(tmp_path, monkeypatch):
    target = tmp_path / 'new.txt'
    sent = []
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, name: sent.append(name))
    scan = engine._scan
    scans = 0

    def received_after_scan(stop):
        nonlocal scans
        scans += 1
        result = scan(stop)
        if scans == 2:
            target.write_bytes(b'remote bytes')
            assert engine.record_received(target)
        return result

    monkeypatch.setattr(engine, '_scan', received_after_scan)
    loop(engine, lambda: None, lambda: None)
    assert sent == []


def test_failed_scan_retains_last_successful_baseline(tmp_path, monkeypatch):
    (tmp_path / 'existing.txt').write_bytes(b'already known')
    sent = []
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, name: sent.append(name))
    scan = engine._scan
    scans = 0

    def failed_scan(stop):
        nonlocal scans
        scans += 1
        if scans == 2:
            raise OSError('controlled unreadable directory')
        return scan(stop)

    monkeypatch.setattr(engine, '_scan', failed_scan)
    loop(engine, lambda: None, lambda: None)
    assert sent == []


@pytest.mark.parametrize('excluded', ['outside', 'subdir', 'missing', 'directory'])
def test_receive_receipts_reject_unwatched_paths(tmp_path, excluded):
    watch = tmp_path / 'watch'
    watch.mkdir()
    targets = {'outside': tmp_path / 'outside.txt', 'subdir': watch / 'nested' / 'child.txt',
               'missing': watch / 'missing.txt', 'directory': watch}
    target = targets[excluded]
    if excluded not in {'missing', 'directory'}:
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b'data')
    engine = FolderSyncEngine(watch_dir=watch, sender=lambda *_: pytest.fail('receipt sent a file'))
    assert engine.record_received(target) is False


@pytest.mark.parametrize('signal', [CancelledError('cancel'), KeyboardInterrupt(), SystemExit(7)])
@pytest.mark.parametrize('boundary', ['scan', 'send', 'receipt'])
def test_wrapped_interruption_propagates_unchanged(tmp_path, monkeypatch, signal, boundary):
    target = tmp_path / 'new.txt'
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda *_: None)

    def interrupted(*_args, **_kwargs):
        raise OSError('controlled carrier') from signal

    if boundary == 'receipt':
        target.write_bytes(b'data')
        monkeypatch.setattr(engine, '_digest', interrupted)
    else:
        monkeypatch.setattr(engine, '_scan' if boundary == 'scan' else '_sender', interrupted)
    with pytest.raises(type(signal)) as caught:
        if boundary == 'receipt':
            engine.record_received(target)
        else:
            loop(engine, lambda: target.write_bytes(b'data'))
    assert caught.value is signal


def test_unreadable_nested_directory_does_not_discard_its_known_files(tmp_path, monkeypatch):
    import os

    nested = tmp_path / 'nested'
    nested.mkdir()
    (nested / 'known.txt').write_bytes(b'already known')
    denied = False
    sent = []
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, name: sent.append(name), include_subdirs=True)
    scandir = os.scandir

    def unavailable(directory):
        if denied and Path(directory) == nested:
            raise PermissionError('controlled inaccessible child')
        return scandir(directory)

    def access(value):
        nonlocal denied
        denied = value

    monkeypatch.setattr(os, 'scandir', unavailable)
    loop(engine, lambda: access(True), lambda: access(False))
    assert sent == []


def test_newer_receipt_equal_to_old_baseline_still_wins_over_local_send_completion(tmp_path):
    target = tmp_path / 'shared.txt'
    target.write_bytes(b'baseline')
    sent = []

    def send(path, _name):
        sent.append(Path(path).read_bytes())
        target.write_bytes(b'baseline')
        assert engine.record_received(target)

    engine = FolderSyncEngine(watch_dir=tmp_path, sender=send)
    loop(engine, lambda: target.write_bytes(b'local edit'), lambda: None)
    assert sent == [b'local edit']


def test_existing_file_receipt_after_scan_defers_its_stale_send(tmp_path, monkeypatch):
    target = tmp_path / 'shared.txt'
    target.write_bytes(b'baseline')
    sent = []
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, name: sent.append(Path(path).read_bytes()))
    scan = engine._scan
    scans = 0

    def received_after_scan(stop):
        nonlocal scans
        scans += 1
        result = scan(stop)
        if scans == 2:
            target.write_bytes(b'new remote bytes')
            assert engine.record_received(target)
        return result

    monkeypatch.setattr(engine, '_scan', received_after_scan)
    loop(engine, lambda: target.write_bytes(b'old local edit'), lambda: None)
    assert sent == []
