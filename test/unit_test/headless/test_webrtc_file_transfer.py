"""The file channel: what a remote peer can and cannot write to this disk.

`webrtc_files` reassembles a viewer's upload into a file under the host's inbox.
The name in the envelope is chosen by the peer, so this module is a filesystem
write driven by remote input, and its docstring says the defence out loud:
"incoming filenames are stripped of any directory components to defeat path
traversal". Nothing tested it -- the module reaches `webrtc_transport`, which
raises ImportError at module level without aiortc, so it could not be imported
on any CI square until the `[webrtc]` extra joined the measured install.

Both halves are exercised here, and then wired to each other: the sender's
output is fed straight into the receiver, which is the only way to check that
the two agree about the protocol their shared docstring describes.
"""
import json

import pytest

from je_auto_control.utils.remote_desktop import webrtc_files
from je_auto_control.utils.remote_desktop.webrtc_files import (
    FileTransferError, FileTransferReceiver, FileTransferSender,
)


class _Bridge:
    """`call_soon` on the real bridge runs the call on the loop thread."""

    def call_soon(self, callback, *args):
        callback(*args)


class _Channel:
    """A DataChannel that keeps what was sent."""

    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setattr(webrtc_files, "get_bridge", _Bridge)


def _begin(name, size, transfer_id="t1"):
    return json.dumps({"type": "file_begin", "name": name, "size": size,
                       "transfer_id": transfer_id})


def _end(transfer_id="t1"):
    return json.dumps({"type": "file_end", "transfer_id": transfer_id})


def _receiver(tmp_path):
    return FileTransferReceiver(tmp_path / "inbox")


# === What the peer may name the file ========================================

@pytest.mark.parametrize("name, written_as", [
    ("report.txt", "report.txt"),
    ("../../../etc/passwd", "passwd"),
    ("a/b/c/nested.bin", "nested.bin"),
    ("./visible.txt", "visible.txt"),
    ("trailing/", "trailing"),
])
def test_a_directory_in_the_name_never_escapes_the_inbox(bridge, tmp_path,
                                                         name, written_as):
    receiver = _receiver(tmp_path)
    receiver.handle_message(_begin(name, 2))
    receiver.handle_message(b"hi")
    receiver.handle_message(_end())
    inbox = tmp_path / "inbox"
    assert [entry.name for entry in inbox.iterdir()] == [written_as]
    assert (inbox / written_as).read_bytes() == b"hi"


@pytest.mark.parametrize("name", ["", ".", "..", "bad\x00name",
                                  "pipe|name", "star*name", "quest?name",
                                  "lt<name", "gt>name", 'quote"name'])
def test_a_name_that_cannot_be_made_safe_is_refused(bridge, tmp_path, name):
    receiver = _receiver(tmp_path)
    errors = []
    receiver.handle_message(_begin(name, 2), on_error=errors.append)
    assert errors, f"{name!r} was accepted"
    assert list((tmp_path / "inbox").iterdir()) == []


def test_a_non_string_name_is_refused(bridge, tmp_path):
    receiver = _receiver(tmp_path)
    errors = []
    receiver.handle_message(
        json.dumps({"type": "file_begin", "name": None, "size": 1}),
        on_error=errors.append)
    assert errors


@pytest.mark.parametrize("size", [-1, 5 * 1024 * 1024 * 1024])
def test_an_impossible_size_is_refused_before_any_file_is_opened(
        bridge, tmp_path, size):
    receiver = _receiver(tmp_path)
    errors = []
    receiver.handle_message(_begin("big.bin", size), on_error=errors.append)
    assert errors
    assert list((tmp_path / "inbox").iterdir()) == []


# === The protocol ===========================================================

def test_a_transfer_arrives_in_pieces_and_reports_progress(bridge, tmp_path):
    receiver = _receiver(tmp_path)
    progress, done = [], []
    receiver.handle_message(_begin("split.bin", 6))
    receiver.handle_message(b"abc", on_progress=lambda n, total:
                            progress.append((n, total)))
    receiver.handle_message(b"def", on_progress=lambda n, total:
                            progress.append((n, total)))
    receiver.handle_message(_end(), on_done=done.append)
    assert progress == [(3, 6), (6, 6)]
    assert done and done[0].read_bytes() == b"abcdef"


@pytest.mark.parametrize("chunk", [b"raw", bytearray(b"raw"),
                                   memoryview(b"raw")])
def test_a_chunk_arrives_however_the_transport_spells_bytes(bridge, tmp_path,
                                                            chunk):
    receiver = _receiver(tmp_path)
    receiver.handle_message(_begin("x.bin", 3))
    receiver.handle_message(chunk)
    receiver.handle_message(_end())
    assert (tmp_path / "inbox" / "x.bin").read_bytes() == b"raw"


def test_a_chunk_with_no_transfer_open_is_dropped(bridge, tmp_path):
    """A late chunk from an aborted transfer must not create a file."""
    receiver = _receiver(tmp_path)
    receiver.handle_message(b"orphan")
    assert list((tmp_path / "inbox").iterdir()) == []


def test_an_end_with_no_transfer_open_is_ignored(bridge, tmp_path):
    receiver = _receiver(tmp_path)
    done = []
    receiver.handle_message(_end(), on_done=done.append)
    assert done == []


def test_a_second_begin_is_refused_and_takes_the_first_with_it(bridge,
                                                              tmp_path):
    """One transfer per channel: the module says so, and it fails closed."""
    receiver = _receiver(tmp_path)
    errors = []
    receiver.handle_message(_begin("first.bin", 10))
    receiver.handle_message(b"partial")
    receiver.handle_message(_begin("second.bin", 10), on_error=errors.append)
    assert errors == ["transfer already in progress"]
    # The partial first file is removed rather than left as a truncated one.
    assert list((tmp_path / "inbox").iterdir()) == []


def test_an_abort_from_the_sender_removes_the_partial_file(bridge, tmp_path):
    receiver = _receiver(tmp_path)
    errors = []
    receiver.handle_message(_begin("partial.bin", 100))
    receiver.handle_message(b"half")
    receiver.handle_message(json.dumps({"type": "file_abort"}),
                            on_error=errors.append)
    assert errors == ["aborted by sender"]
    assert list((tmp_path / "inbox").iterdir()) == []


def test_an_abort_with_nothing_in_flight_is_harmless(bridge, tmp_path):
    receiver = _receiver(tmp_path)
    receiver.handle_message(json.dumps({"type": "file_abort"}))
    assert list((tmp_path / "inbox").iterdir()) == []


def test_a_malformed_envelope_is_reported_not_raised(bridge, tmp_path):
    receiver = _receiver(tmp_path)
    errors = []
    receiver.handle_message("{not json", on_error=errors.append)
    assert errors and "bad envelope" in errors[0]


def test_an_unknown_envelope_type_is_ignored(bridge, tmp_path):
    receiver = _receiver(tmp_path)
    receiver.handle_message(json.dumps({"type": "file_pause"}))
    assert list((tmp_path / "inbox").iterdir()) == []


def test_a_message_that_is_neither_text_nor_bytes_is_ignored(bridge, tmp_path):
    receiver = _receiver(tmp_path)
    receiver.handle_message(42)
    assert list((tmp_path / "inbox").iterdir()) == []


def test_the_inbox_is_created_on_construction(bridge, tmp_path):
    inbox = tmp_path / "deep" / "inbox"
    FileTransferReceiver(inbox)
    assert inbox.is_dir()


# === The sending half =======================================================

def test_a_sender_needs_a_channel():
    with pytest.raises(ValueError):
        FileTransferSender(None)


def test_sending_a_path_that_is_not_a_file_is_refused(bridge, tmp_path):
    sender = FileTransferSender(_Channel())
    with pytest.raises(FileTransferError, match="not a file"):
        sender.send(tmp_path / "missing.txt")
    with pytest.raises(FileTransferError, match="not a file"):
        sender.send(tmp_path)


def test_a_send_is_a_begin_then_chunks_then_an_end(bridge, tmp_path):
    source = tmp_path / "payload.bin"
    source.write_bytes(b"0123456789")
    channel = _Channel()
    progress = []
    FileTransferSender(channel).send(source, chunk_size=4,
                                     on_progress=lambda n, total:
                                     progress.append((n, total)))
    begin = json.loads(channel.messages[0])
    assert begin["type"] == "file_begin"
    assert begin["name"] == "payload.bin"
    assert begin["size"] == 10
    assert channel.messages[1:-1] == [b"0123", b"4567", b"89"]
    end = json.loads(channel.messages[-1])
    assert end["type"] == "file_end"
    assert end["transfer_id"] == begin["transfer_id"]
    assert progress == [(4, 10), (8, 10), (10, 10)]


def test_an_empty_file_is_a_begin_and_an_end_with_no_chunks(bridge, tmp_path):
    source = tmp_path / "empty.bin"
    source.write_bytes(b"")
    channel = _Channel()
    FileTransferSender(channel).send(source)
    assert [json.loads(message)["type"] for message in channel.messages] == [
        "file_begin", "file_end"]


def test_the_remote_name_is_sanitised_before_it_leaves(bridge, tmp_path):
    """The sender is the other side's remote peer; it does not get to say
    where its file lands either."""
    source = tmp_path / "payload.bin"
    source.write_bytes(b"x")
    channel = _Channel()
    FileTransferSender(channel).send(source, remote_name="a/b/../evil.txt")
    assert json.loads(channel.messages[0])["name"] == "evil.txt"


def test_a_read_failure_mid_transfer_aborts_the_receiver_too(bridge, tmp_path):
    source = tmp_path / "payload.bin"
    source.write_bytes(b"0123456789")

    class _Failing:
        def __init__(self, real):
            self._real = real
            self._reads = 0

        def read(self, size):
            self._reads += 1
            if self._reads > 1:
                raise OSError("device disappeared")
            return self._real.read(size)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._real.close()
            return False

    real_open = type(source).open

    def _open(self, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)
        return _Failing(handle) if self == source else handle

    channel = _Channel()
    monkey = pytest.MonkeyPatch()
    monkey.setattr(type(source), "open", _open)
    try:
        with pytest.raises(FileTransferError, match="read failed"):
            FileTransferSender(channel).send(source, chunk_size=4)
    finally:
        monkey.undo()
    assert json.loads(channel.messages[-1])["type"] == "file_abort"


# === The two halves agree ===================================================

def test_a_file_survives_a_round_trip_through_the_protocol(bridge, tmp_path):
    """Neither side's view of the protocol is asserted from the other's code."""
    source = tmp_path / "round.bin"
    source.write_bytes(bytes(range(256)) * 40)      # 10,240 bytes
    receiver = _receiver(tmp_path)
    done = []

    class _Wired:
        def send(self, message):
            receiver.handle_message(message, on_done=done.append)

    FileTransferSender(_Wired()).send(source, remote_name="landed.bin",
                                      chunk_size=1024)
    assert done, "the receiver never completed the transfer"
    assert done[0].name == "landed.bin"
    assert done[0].read_bytes() == source.read_bytes()


def test_an_aborted_send_leaves_nothing_behind_on_the_receiver(bridge,
                                                               tmp_path):
    receiver = _receiver(tmp_path)

    class _Wired:
        def send(self, message):
            receiver.handle_message(message)

    channel = _Wired()
    receiver.handle_message(_begin("stale.bin", 100))
    receiver.handle_message(b"partial")
    channel.send(json.dumps({"type": "file_abort"}))
    assert list((tmp_path / "inbox").iterdir()) == []
