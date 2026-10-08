"""The echo guards are called by the code that receives, not only by their tests.

``FolderSyncEngine.note_received`` and ``ClipboardEchoGuard`` existed with
tests and no callers: a file that arrived in a mirrored folder was pushed
straight back, and nothing recorded which clipboard content had come from the
peer. The mirror also pushed a file while it was still being written -- the
receiver's own ``.name.<id>.part`` files included.
"""
import hashlib
import json
import os
import time

import pytest

from je_auto_control.utils.remote_desktop import file_sync
from je_auto_control.utils.remote_desktop.clipboard_sync import ClipboardEchoGuard
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine, note_incoming
from je_auto_control.utils.remote_desktop.file_transfer import (
    FileReceiver, encode_begin, encode_chunk, encode_end,
)
from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer


def _wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture
def watch(tmp_path):
    folder = tmp_path / "watch"
    folder.mkdir()
    return folder


def _engine(watch, sent, **options):
    engine = FolderSyncEngine(watch_dir=watch, sender=lambda _path, name: sent.append(name),
                              **options)
    engine.poll_once()                  # the baseline
    return engine


def _polls(engine, count=3):
    pushed = []
    for _ in range(count):
        pushed.extend(engine.poll_once())
    return pushed


# --- a file still being written ------------------------------------------------

def test_a_file_is_pushed_only_once_it_stopped_changing(watch):
    sent = []
    engine = _engine(watch, sent)
    target = watch / "big.bin"
    target.write_bytes(b"half")
    assert engine.poll_once() == [], "first sight: it may still be growing"
    target.write_bytes(b"half and the rest")
    os.utime(target, (time.time() + 5, time.time() + 5))
    assert engine.poll_once() == [], "it changed since the last poll: still being written"
    assert engine.poll_once() == ["big.bin"], "same size and mtime on two polls"
    assert engine.poll_once() == [] and sent == ["big.bin"]


def test_the_wait_can_be_turned_off(watch):
    sent = []
    engine = _engine(watch, sent, wait_until_stable=False)
    (watch / "now.txt").write_text("x", encoding="utf-8")
    assert engine.poll_once() == ["now.txt"]


@pytest.mark.parametrize("name", [".report.pdf.1a2b3c4d.part", "movie.mkv.part",
                                  "export.tmp", "setup.exe.crdownload", "a.partial"])
def test_in_progress_names_are_never_mirrored(watch, name):
    sent = []
    engine = _engine(watch, sent)
    (watch / name).write_bytes(b"partial")
    assert _polls(engine) == [] and sent == []
    # The sender's convention: write under such a name, rename when complete.
    os.replace(watch / name, watch / "done.bin")
    assert _polls(engine) == ["done.bin"]


def test_a_failed_push_is_still_retried(watch):
    attempts = []

    def flaky(_path, name):
        attempts.append(name)
        if len(attempts) == 1:
            raise OSError("transient")

    engine = FolderSyncEngine(watch_dir=watch, sender=flaky)
    engine.poll_once()
    (watch / "retry.txt").write_text("data", encoding="utf-8")
    assert _polls(engine, 4) == ["retry.txt"] and attempts == ["retry.txt", "retry.txt"]


# --- received files are noted by the receivers ------------------------------------

def test_a_file_the_webrtc_receiver_writes_into_a_mirror_is_not_pushed_back(watch):
    # webrtc_files imports the WebRTC transport, which needs the [webrtc] extra.
    pytest.importorskip("aiortc", exc_type=ImportError)
    from je_auto_control.utils.remote_desktop.webrtc_files import FileTransferReceiver
    sent = []
    engine = _engine(watch, sent)
    receiver = FileTransferReceiver(inbox_dir=watch)
    done = []
    receiver.handle_message(json.dumps(
        {"type": "file_begin", "name": "from-peer.txt", "size": 5, "transfer_id": "t1"}))
    assert _polls(engine, 2) == [], "the part file is not mirrored while it is written"
    receiver.handle_message(b"hello")
    receiver.handle_message(json.dumps({"type": "file_end"}), on_done=done.append)
    assert done and (watch / "from-peer.txt").read_bytes() == b"hello"
    assert _polls(engine) == [] and sent == []
    # A local edit afterwards is this machine's change again -- even in the
    # clock tick the file arrived in: the mirror compares what it recorded,
    # not only whether the time moved on.
    (watch / "from-peer.txt").write_bytes(b"edited here")
    assert _polls(engine) == ["from-peer.txt"]


def test_a_file_the_tcp_receiver_writes_into_a_mirror_is_not_pushed_back(watch):
    sent = []
    engine = _engine(watch, sent)
    outcome = []
    receiver = FileReceiver(base_dir=watch,
                            on_complete=lambda *result: outcome.append(result))
    transfer_id = "0f8fad5b-d9cb-469f-a165-70867728950e"
    receiver.handle_begin(encode_begin(transfer_id, "from-peer.bin", 3))
    receiver.handle_chunk(encode_chunk(transfer_id, b"abc"))
    assert _polls(engine, 2) == []
    receiver.handle_end(encode_end(transfer_id))
    assert outcome and outcome[0][1] is True
    assert _polls(engine) == [] and sent == []


def test_a_mirror_of_another_folder_is_not_told(watch, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    engine = _engine(watch, [])
    arrived = other / "x.bin"
    arrived.write_bytes(b"x")
    assert note_incoming(arrived) == 0
    assert engine._received == {}  # noqa: SLF001
    inside = watch / "y.bin"
    inside.write_bytes(b"y")
    assert note_incoming(inside) == 1
    assert engine._received == {"y.bin": hashlib.sha256(b"y").hexdigest()}  # noqa: SLF001


def test_a_subfolder_is_only_covered_when_the_mirror_includes_subfolders(watch):
    (watch / "sub").mkdir()
    flat = _engine(watch, [])
    deep = _engine(watch, [], include_subdirs=True)
    nested = watch / "sub" / "z.bin"
    nested.write_bytes(b"z")
    assert note_incoming(nested) == 1
    assert flat._received == {} and list(deep._received) == ["sub/z.bin"]  # noqa: SLF001


def test_a_stopped_and_forgotten_engine_is_not_kept_alive(watch):
    import gc
    import weakref
    engine = _engine(watch, [])
    assert engine in file_sync.live_engines()
    alive = weakref.ref(engine)
    del engine
    gc.collect()
    assert alive() is None, "the registry of engines must not keep one alive"


# --- clipboard ---------------------------------------------------------------------

def test_the_guard_records_an_explicit_send():
    guard = ClipboardEchoGuard()
    guard.note_sent("text", "copied here")
    assert guard.should_send("text", "copied here") is False
    assert guard.should_send("text", "something new") is True


class _RecordingHost(RemoteDesktopHost):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.applied = []

    def _apply_clipboard(self, kind, data):
        self.applied.append((kind, data))


@pytest.fixture
def host():
    running = _RecordingHost(token="tok", bind="127.0.0.1", port=0, fps=50.0,
                             frame_provider=lambda: b"frame",
                             input_dispatcher=lambda *_a, **_k: None, host_id="900800700")
    running.start()
    yield running
    running.stop(timeout=1.0)


def _viewer(host, received):
    viewer = RemoteDesktopViewer(
        host="127.0.0.1", port=host.port, token="tok",
        on_clipboard=lambda kind, data: received.append((kind, data)))
    viewer.connect(timeout=10.0)
    return viewer


def test_the_host_does_not_forward_back_what_a_viewer_just_sent(host):
    received = []
    viewer = _viewer(host, received)
    try:
        assert _wait_until(lambda: host.connected_clients == 1)
        viewer.send_clipboard_text("from the viewer")
        assert _wait_until(lambda: host.applied == [("text", "from the viewer")])
        # A watcher on the host sees its clipboard change and forwards it.
        assert host.broadcast_clipboard_text("from the viewer", automatic=True) == 0
        assert host.broadcast_clipboard_text("typed on the host", automatic=True) == 1
        assert _wait_until(lambda: received == [("text", "typed on the host")])
        # Still on the clipboard at the next look: not sent a second time.
        assert host.broadcast_clipboard_text("typed on the host", automatic=True) == 0
    finally:
        viewer.disconnect()


def test_an_explicit_send_always_goes_and_is_remembered(host):
    received = []
    viewer = _viewer(host, received)
    try:
        assert _wait_until(lambda: host.connected_clients == 1)
        assert host.broadcast_clipboard_text("pressed send") == 1
        assert host.broadcast_clipboard_text("pressed send") == 1, "a person asked twice"
        assert _wait_until(lambda: len(received) == 2)
        assert host.broadcast_clipboard_text("pressed send", automatic=True) == 0
    finally:
        viewer.disconnect()


def test_what_one_viewer_sent_still_reaches_the_other(host):
    first_received, second_received = [], []
    first = _viewer(host, first_received)
    second = _viewer(host, second_received)
    try:
        assert _wait_until(lambda: host.connected_clients == 2)
        first.send_clipboard_text("shared")
        assert _wait_until(lambda: host.applied == [("text", "shared")])
        assert host.broadcast_clipboard_text("shared", automatic=True) == 1
        assert _wait_until(lambda: second_received == [("text", "shared")])
        assert first_received == []
    finally:
        first.disconnect()
        second.disconnect()


def test_the_viewer_does_not_send_back_what_the_host_just_sent(host):
    received = []
    viewer = _viewer(host, received)
    try:
        assert _wait_until(lambda: host.connected_clients == 1)
        host.broadcast_clipboard_text("from the host")
        assert _wait_until(lambda: received == [("text", "from the host")])
        assert viewer.send_clipboard_text("from the host", automatic=True) is False
        assert viewer.send_clipboard_text("typed on the viewer", automatic=True) is True
        assert _wait_until(lambda: ("text", "typed on the viewer") in host.applied)
        assert viewer.send_clipboard_text("typed on the viewer", automatic=True) is False
        # An explicit send is never held back.
        assert viewer.send_clipboard_text("from the host") is True
        assert viewer.send_clipboard_image(b"\x89PNGfake", automatic=True) is True
        assert viewer.send_clipboard_image(b"\x89PNGfake", automatic=True) is False
    finally:
        viewer.disconnect()


def test_a_reconnect_forgets_what_the_last_session_exchanged(host):
    received = []
    viewer = _viewer(host, received)
    try:
        assert viewer.send_clipboard_text("before", automatic=True) is True
        viewer.disconnect()
        viewer.connect(timeout=10.0)
        # The peer may hold anything now: the same content is news again.
        assert viewer.send_clipboard_text("before", automatic=True) is True
    finally:
        viewer.disconnect()
