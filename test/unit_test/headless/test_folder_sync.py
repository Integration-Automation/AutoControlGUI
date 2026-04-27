"""Tests for FolderSyncEngine (round 22 — additive folder mirror)."""
import time

import pytest

from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine


@pytest.fixture()
def watch_dir(tmp_path):
    return tmp_path


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
        time.sleep(0.5)  # one tick
    finally:
        engine.stop()
    assert sent == [], f"pre-existing file leaked: {sent}"


def test_new_file_is_pushed(watch_dir):
    sent = []
    engine = _make_engine(watch_dir, lambda p, n: sent.append(n))
    engine.start()
    try:
        time.sleep(0.4)  # let initial snapshot settle
        (watch_dir / "new.txt").write_text("hi", encoding="utf-8")
        time.sleep(0.6)
    finally:
        engine.stop()
    assert "new.txt" in sent, sent


def test_modified_file_is_pushed_again(watch_dir):
    sent = []
    target = watch_dir / "doc.txt"
    target.write_text("v1", encoding="utf-8")
    engine = _make_engine(watch_dir, lambda p, n: sent.append(n))
    engine.start()
    try:
        time.sleep(0.4)
        # bump mtime forward so the diff fires
        future = target.stat().st_mtime + 5.0
        target.write_text("v2", encoding="utf-8")
        import os
        os.utime(target, (future, future))
        time.sleep(0.6)
    finally:
        engine.stop()
    assert sent.count("doc.txt") == 1


def test_deletion_does_not_propagate(watch_dir):
    """Sync is additive-only — deleting locally must not call the sender."""
    sent = []
    target = watch_dir / "kept.txt"
    target.write_text("payload", encoding="utf-8")
    engine = _make_engine(watch_dir, lambda p, n: sent.append(n))
    engine.start()
    try:
        time.sleep(0.4)
        target.unlink()
        time.sleep(0.6)
    finally:
        engine.stop()
    assert sent == [], f"deletion was propagated: {sent}"


def test_sender_failure_is_retried_next_tick(watch_dir):
    """A raising sender on the first tick must not poison the snapshot."""
    attempts = []

    def flaky_sender(local_path, remote_name):
        attempts.append(remote_name)
        if len(attempts) == 1:
            raise RuntimeError("transient")

    engine = _make_engine(watch_dir, flaky_sender)
    engine.start()
    try:
        time.sleep(0.7)
        (watch_dir / "retry.txt").write_text("data", encoding="utf-8")
        # Engine clamps interval to 0.5s minimum, so wait ≥1.5s for two ticks.
        time.sleep(1.7)
    finally:
        engine.stop()
    assert len(attempts) >= 2, attempts
    assert all(name == "retry.txt" for name in attempts)


def test_start_rejects_missing_dir(tmp_path):
    missing = tmp_path / "does-not-exist"
    engine = _make_engine(missing, lambda p, n: None)
    with pytest.raises(FileNotFoundError):
        engine.start()
