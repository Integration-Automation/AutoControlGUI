"""Deterministic folder mirroring contracts for content, retry and stopped-run ownership."""
import os
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest

from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine


class Ticks:
    """Run explicit filesystem/connection transitions between polling ticks."""

    def __init__(self, callbacks):
        self.callbacks = list(callbacks)
        self.stopped = False

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True

    def wait(self, _timeout):
        if self.callbacks:
            self.callbacks.pop(0)()
        else:
            self.set()
        return self.stopped


def loop(engine, *callbacks):
    engine._loop(Ticks(callbacks))


@pytest.mark.parametrize('mtime_delta', [0, -10])
def test_changed_bytes_with_equal_or_older_mtime_are_delivered(tmp_path, mtime_delta):
    target = tmp_path / 'document.txt'
    target.write_bytes(b'old')
    before = target.stat()
    sent = []
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, name: sent.append(Path(path).read_bytes()))

    def edited():
        target.write_bytes(b'new')
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns + mtime_delta * 10**9))

    loop(engine, edited)
    assert sent == [b'new']


def test_timestamp_only_change_does_not_retransmit_unchanged_content(tmp_path):
    target = tmp_path / 'document.txt'
    target.write_bytes(b'same content')
    before = target.stat()
    sent = []
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, name: sent.append(name))
    loop(engine, lambda: os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns + 10**9)))
    assert sent == []


def test_stop_during_first_send_does_not_dispatch_remaining_files(tmp_path):
    sent = []
    ticks = Ticks([lambda: [(tmp_path / name).write_bytes(b'data') for name in ('one.txt', 'two.txt')]])

    def send(_path, name):
        sent.append(name)
        ticks.set()

    engine = FolderSyncEngine(watch_dir=tmp_path, sender=send)
    engine._loop(ticks)
    assert len(sent) == 1


def test_stop_from_sender_callback_does_not_join_its_own_thread(tmp_path):
    finished = Event()
    errors = []

    def send(_path, _name):
        try:
            engine.stop()
        except RuntimeError as error:
            errors.append(error)
        finally:
            finished.set()

    engine = FolderSyncEngine(watch_dir=tmp_path, sender=send)
    engine._interval = .001
    engine.start()
    try:
        assert engine.wait_until_ready()
        (tmp_path / 'new.txt').write_bytes(b'data')
        assert finished.wait(5)
        assert errors == []
    finally:
        engine.stop()


def test_timed_out_stop_retains_worker_and_prevents_overlapping_restart(tmp_path):
    entered, release = Event(), Event()

    def send(_path, _name):
        entered.set()
        assert release.wait(5)

    engine = FolderSyncEngine(watch_dir=tmp_path, sender=send)
    engine._interval = .001
    engine.start()
    worker = engine._thread
    try:
        assert engine.wait_until_ready()
        (tmp_path / 'new.txt').write_bytes(b'data')
        assert entered.wait(5)
        with patch.object(worker, 'join', lambda timeout: None):
            engine.stop()
        assert engine.is_running(), 'the stopped but blocked worker must remain owned'
        engine.start()
        assert engine._thread is worker, 'a second run overlapped the stopped sender'
        assert not engine.wait_until_ready(0)
    finally:
        release.set()
        worker.join(5)
        engine.stop()
    engine.start()
    try:
        assert engine.wait_until_ready()
        assert engine._thread is not worker
    finally:
        engine.stop()


def test_disconnected_sender_retries_current_bytes_after_reconnection(tmp_path):
    connected = False
    attempts = []
    delivered = []
    target = tmp_path / 'pending.txt'

    def send(path, name):
        attempts.append(name)
        if not connected:
            raise ConnectionError('controlled disconnect')
        delivered.append(Path(path).read_bytes())

    def reconnect():
        nonlocal connected
        target.write_bytes(b'latest local edit')
        connected = True

    engine = FolderSyncEngine(watch_dir=tmp_path, sender=send)
    loop(engine, lambda: target.write_bytes(b'pending'), lambda: None, reconnect, lambda: None)
    assert attempts == ['pending.txt'] * 3
    assert delivered == [b'latest local edit']


def test_restart_delivers_failed_and_offline_edits_instead_of_rebaselining_them(tmp_path):
    target = tmp_path / 'pending.txt'
    sent = []
    attempts = Event()

    def disconnected(_path, _name):
        attempts.set()
        raise ConnectionError('controlled disconnect')

    engine = FolderSyncEngine(watch_dir=tmp_path, sender=disconnected)
    engine._interval = .001
    engine.start()
    try:
        assert engine.wait_until_ready()
        target.write_bytes(b'pending')
        assert attempts.wait(5)
    finally:
        engine.stop()
    target.write_bytes(b'offline edit')
    delivered = Event()

    def connected(path, _name):
        sent.append(Path(path).read_bytes())
        delivered.set()

    engine._sender = connected
    engine.start()
    try:
        assert engine.wait_until_ready()
        assert delivered.wait(5), 'restart treated a pending file as an already-delivered baseline'
        assert sent == [b'offline edit']
    finally:
        engine.stop()
