"""The folder mirror notices an edit made in the clock tick it last looked in.

``FolderSyncEngine`` called a file changed only when its modification time was
*later* than the one it had recorded. A local edit that landed in the same
tick as the recorded state -- seen in CI right after a received file had been
noted as an echo -- kept the same time and was never pushed. The engine now
compares what it recorded (time and size), and for a file recorded so soon
after its last write that the time cannot tell two writes apart, its content.

The clock is never raced here: the file's time is pinned with ``os.utime``
and the engine's idea of "now" is replaced.
"""
import hashlib
import os

import pytest

from je_auto_control.utils.remote_desktop import file_sync
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine

_TICK_NS = 1_700_000_000_000_000_000
_SECOND_NS = 1_000_000_000


@pytest.fixture
def watch(tmp_path):
    folder = tmp_path / "watch"
    folder.mkdir()
    return folder


@pytest.fixture
def clock(monkeypatch):
    """The engine's wall clock, as a one-item list the test moves."""
    now = [_TICK_NS]
    monkeypatch.setattr(file_sync, "_wall_ns", lambda: now[0])
    return now


def _write(path, data, tick_ns=_TICK_NS):
    """Write ``data`` and pin the file's time, so two writes share one tick."""
    path.write_bytes(data)
    os.utime(path, ns=(tick_ns, tick_ns))


def _engine(watch, sent, **options):
    options.setdefault("wait_until_stable", False)
    engine = FolderSyncEngine(watch_dir=watch, sender=lambda _path, name: sent.append(name),
                              **options)
    engine.poll_once()                  # the baseline
    return engine


def test_an_edit_of_another_size_in_the_same_tick_is_pushed(watch, clock):
    sent = []
    engine = _engine(watch, sent)
    _write(watch / "a.txt", b"first")
    assert engine.poll_once() == ["a.txt"]
    _write(watch / "a.txt", b"second, and longer")
    assert engine.poll_once() == ["a.txt"]
    assert engine.poll_once() == [] and sent == ["a.txt", "a.txt"]


def test_an_edit_of_the_same_size_in_the_same_tick_is_pushed(watch, clock):
    sent = []
    engine = _engine(watch, sent)
    _write(watch / "a.txt", b"first")
    assert engine.poll_once() == ["a.txt"]
    _write(watch / "a.txt", b"FIRST")
    assert engine.poll_once() == ["a.txt"], "same time, same size: only the content differs"
    assert engine.poll_once() == []


def test_an_edit_in_the_tick_a_received_file_was_noted_in_is_pushed(watch, clock):
    sent = []
    engine = _engine(watch, sent)
    incoming = b"from peer"
    engine.note_received("r.txt", sha256=hashlib.sha256(incoming).hexdigest())
    _write(watch / "r.txt", incoming)
    assert engine.poll_once() == [] and sent == [], "what the peer sent is not pushed back"
    _write(watch / "r.txt", b"FROM HERE")       # same size, same tick
    assert engine.poll_once() == ["r.txt"]
    assert engine.poll_once() == []


def test_a_file_already_there_at_the_baseline_and_edited_in_that_tick_is_pushed(watch, clock):
    _write(watch / "old.txt", b"before")
    sent = []
    engine = _engine(watch, sent)
    assert engine.poll_once() == []
    _write(watch / "old.txt", b"BEFORE")
    assert engine.poll_once() == ["old.txt"]


def test_a_file_put_back_with_an_older_time_is_pushed(watch, clock):
    sent = []
    engine = _engine(watch, sent)
    _write(watch / "a.txt", b"new copy")
    assert engine.poll_once() == ["a.txt"]
    _write(watch / "a.txt", b"restored", tick_ns=_TICK_NS - 3600 * _SECOND_NS)
    assert engine.poll_once() == ["a.txt"], "an older time is still a different file"


def test_a_failed_push_in_the_same_tick_is_still_retried(watch, clock):
    attempts = []

    def flaky(_path, name):
        attempts.append(name)
        if len(attempts) == 1:
            raise OSError("transient")

    engine = FolderSyncEngine(watch_dir=watch, sender=flaky, wait_until_stable=False)
    engine.poll_once()
    _write(watch / "a.txt", b"data")
    assert engine.poll_once() == []
    assert engine.poll_once() == ["a.txt"] and attempts == ["a.txt", "a.txt"]


def test_waiting_until_stable_still_holds_a_changing_file_back(watch, clock):
    sent = []
    engine = _engine(watch, sent, wait_until_stable=True)
    _write(watch / "big.bin", b"half")
    assert engine.poll_once() == [], "first sight: it may still be growing"
    _write(watch / "big.bin", b"half and the rest")
    assert engine.poll_once() == [], "it changed since the last poll"
    assert engine.poll_once() == ["big.bin"]
    assert engine.poll_once() == []


def test_content_is_read_only_while_the_time_cannot_be_trusted(watch, clock, monkeypatch):
    read = []
    real = file_sync._file_digest

    def counting(path):
        read.append(path.name)
        return real(path)

    monkeypatch.setattr(file_sync, "_file_digest", counting)
    sent = []
    engine = _engine(watch, sent)
    _write(watch / "a.txt", b"first")
    assert engine.poll_once() == ["a.txt"]
    assert engine.poll_once() == [] and read, "written this tick: compared by content"
    # Long after the write, a later edit cannot share its tick any more.
    clock[0] = _TICK_NS + 60 * _SECOND_NS
    assert engine.poll_once() == []
    del read[:]
    assert engine.poll_once() == [] and read == [], "an old file is compared by time and size"
    # A file that was already old when first seen is never read at all.
    _write(watch / "old.txt", b"old", tick_ns=_TICK_NS - 3600 * _SECOND_NS)
    assert engine.poll_once() == ["old.txt"]
    assert engine.poll_once() == [] and read == []
