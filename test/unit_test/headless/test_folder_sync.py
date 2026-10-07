"""Tests for FolderSyncEngine (round 22 — additive folder mirror)."""
import os
from pathlib import Path
import time
import threading

import pytest

from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine


@pytest.fixture()
def watch_dir(tmp_path):
    """A dedicated watch dir, so a test can stage files beside it."""
    target = tmp_path / "watch"
    target.mkdir()
    return target


def _make_engine(watch, sender, *, interval=0.2, include_subdirs=False):
    return FolderSyncEngine(
        watch_dir=watch, sender=sender,
        poll_interval_s=interval, include_subdirs=include_subdirs,
    )


def test_pre_existing_files_not_pushed(watch_dir):
    """Initial snapshot must not re-upload files that were already there."""
    sent = []
    (watch_dir / "old.txt").write_text("legacy", encoding="utf-8")
    engine = _make_engine(watch_dir, lambda p, n: sent.append(n))
    engine.start()
    try:
        assert engine.wait_until_ready()
        time.sleep(0.5)  # one tick
    finally:
        engine.stop()
    assert sent == [], f"pre-existing file leaked: {sent}"


def test_new_file_is_pushed(watch_dir):
    sent = []
    completed = threading.Event()

    def sender(_path, name):
        sent.append(name)
        completed.set()

    engine = _make_engine(watch_dir, sender)
    engine.start()
    try:
        assert engine.wait_until_ready()  # baseline is fixed from here on
        (watch_dir / "new.txt").write_text("hi", encoding="utf-8")
        # Stable content needs two polls; debugger scheduling must not race a fixed sleep.
        assert completed.wait(5)
    finally:
        engine.stop()
    assert "new.txt" in sent, sent


def test_modified_file_is_pushed_again(watch_dir, tmp_path):
    sent = []
    payloads = []
    completed = threading.Event()

    def sender(path, name):
        payloads.append(Path(path).read_text(encoding='utf-8'))
        sent.append(name)
        completed.set()

    target = watch_dir / "doc.txt"
    target.write_text("v1", encoding="utf-8")
    engine = _make_engine(watch_dir, sender)
    engine.start()
    try:
        assert engine.wait_until_ready()
        # Bump mtime forward so the diff fires, but stage the new content
        # *outside* the watch dir and swap it in atomically. Writing in
        # place exposes an intermediate mtime between write and utime, and
        # a tick landing in that window counts the edit twice.
        future = target.stat().st_mtime + 5.0
        staged = tmp_path / "doc.txt.staged"
        staged.write_text("v2", encoding="utf-8")
        os.utime(staged, (future, future))
        os.replace(staged, target)
        assert completed.wait(5)
    finally:
        engine.stop()
    assert sent.count("doc.txt") == 1, sent
    assert payloads == ['v2']


def test_deletion_does_not_propagate(watch_dir):
    """Sync is additive-only — deleting locally must not call the sender."""
    sent = []
    target = watch_dir / "kept.txt"
    target.write_text("payload", encoding="utf-8")
    engine = _make_engine(watch_dir, lambda p, n: sent.append(n))
    engine.start()
    try:
        assert engine.wait_until_ready()
        target.unlink()
        time.sleep(1.1)
    finally:
        engine.stop()
    assert sent == [], f"deletion was propagated: {sent}"


def test_sender_failure_is_retried_next_tick(watch_dir):
    """A raising sender on the first tick must not poison the snapshot."""
    attempts = []
    completed = threading.Event()

    def flaky_sender(local_path, remote_name):
        attempts.append(remote_name)
        if len(attempts) == 1:
            raise RuntimeError("transient")
        completed.set()

    engine = _make_engine(watch_dir, flaky_sender)
    engine.start()
    try:
        assert engine.wait_until_ready()
        (watch_dir / "retry.txt").write_text("data", encoding="utf-8")
        # Wait for actual success after the failed send; stable content needs two initial polls.
        assert completed.wait(5)
    finally:
        engine.stop()
    assert len(attempts) >= 2, attempts
    assert all(name == "retry.txt" for name in attempts)


def test_start_rejects_missing_dir(tmp_path):
    missing = tmp_path / "does-not-exist"
    engine = _make_engine(missing, lambda p, n: None)
    with pytest.raises(FileNotFoundError):
        engine.start()
