"""File-transfer protocol + host<->viewer integration tests."""
import time
from pathlib import Path

import pytest

from je_auto_control.utils.remote_desktop import (
    FileReceiver, FileTransferError, RemoteDesktopHost, RemoteDesktopViewer,
    send_file,
)
from je_auto_control.utils.remote_desktop.file_transfer import (
    decode_begin, decode_chunk, decode_end, encode_begin, encode_chunk,
    encode_end, new_transfer_id,
)


def _wait_until(predicate, timeout: float = 4.0,
                interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# --- serialization unit tests --------------------------------------------


def test_begin_round_trip():
    tid = new_transfer_id()
    payload = encode_begin(tid, "/tmp/a.bin", 4242)
    out_id, dest, size = decode_begin(payload)
    assert out_id == tid
    assert dest == "/tmp/a.bin"
    assert size == 4242


def test_chunk_round_trip():
    tid = new_transfer_id()
    payload = encode_chunk(tid, b"\x01\x02\x03\x04")
    out_id, body = decode_chunk(payload)
    assert out_id == tid
    assert body == b"\x01\x02\x03\x04"


def test_end_round_trip_includes_error():
    tid = new_transfer_id()
    out_id, status, error = decode_end(
        encode_end(tid, status="error", error="disk full")
    )
    assert (out_id, status, error) == (tid, "error", "disk full")


def test_decode_chunk_short_payload_raises():
    with pytest.raises(FileTransferError):
        decode_chunk(b"too-short")


def test_encode_begin_rejects_invalid_id():
    with pytest.raises(FileTransferError):
        encode_begin("short", "/tmp/x", 1)


# --- send_file <-> FileReceiver in-process round-trip --------------------


class _BufferChannel:
    """Deliver typed messages directly into a receiver for unit testing."""

    def __init__(self, receiver: FileReceiver) -> None:
        self._receiver = receiver

    def send_typed(self, message_type, payload) -> None:
        from je_auto_control.utils.remote_desktop.protocol import MessageType
        if message_type is MessageType.FILE_BEGIN:
            self._receiver.handle_begin(payload)
        elif message_type is MessageType.FILE_CHUNK:
            self._receiver.handle_chunk(payload)
        elif message_type is MessageType.FILE_END:
            self._receiver.handle_end(payload)
        else:
            raise AssertionError(f"unexpected message {message_type!r}")


def test_send_file_to_receiver_writes_dest(tmp_path: Path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"hello world" * 1000)
    dest = tmp_path / "dst" / "out.bin"

    completes = []
    progress = []
    receiver = FileReceiver(
        on_progress=lambda tid, done, total: progress.append((tid, done, total)),
        on_complete=lambda tid, ok, err, dst: completes.append((tid, ok, err, dst)),
    )
    channel = _BufferChannel(receiver)

    result = send_file(channel, str(src), str(dest))
    assert result.success is True
    assert result.bytes_sent == src.stat().st_size
    assert dest.read_bytes() == src.read_bytes()
    assert completes and completes[-1][1] is True
    # Progress is reported at start (0) and after each chunk; final value
    # equals the file size.
    assert progress[-1][1] == src.stat().st_size


def test_send_file_missing_source_raises(tmp_path: Path):
    receiver = FileReceiver()
    channel = _BufferChannel(receiver)
    with pytest.raises(FileTransferError):
        send_file(channel, str(tmp_path / "missing.bin"),
                  str(tmp_path / "out.bin"))


# --- end-to-end host<->viewer over a real TCP socket --------------------


def _start_host() -> RemoteDesktopHost:
    host = RemoteDesktopHost(
        token="tok", bind="127.0.0.1", port=0, fps=50.0,
        frame_provider=lambda: b"frame",
        input_dispatcher=lambda *_a, **_k: None,
        host_id="333222111",
    )
    host.start()
    return host


def test_viewer_uploads_file_to_host_dropbox(tmp_path: Path):
    payload = b"upload from viewer\n" * 5000
    src = tmp_path / "viewer_src.bin"
    src.write_bytes(payload)
    dest = tmp_path / "host_drop" / "result.bin"

    host_completes = []
    host_progress = []
    host = _start_host()
    host.set_file_receiver(FileReceiver(
        on_progress=lambda *args: host_progress.append(args),
        on_complete=lambda *args: host_completes.append(args),
    ))
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
        )
        viewer.connect(timeout=2.0)
        result = viewer.send_file(str(src), str(dest))
        assert result.success is True
        assert _wait_until(lambda: bool(host_completes))
        tid, ok, err, written_path = host_completes[-1]
        assert ok is True
        assert err is None
        assert Path(written_path) == dest
        assert dest.read_bytes() == payload
        # Progress fired with at least the final byte count
        assert host_progress[-1][1] == len(payload)
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_host_pushes_file_to_viewer(tmp_path: Path):
    payload = b"download from host\n" * 5000
    src = tmp_path / "host_src.bin"
    src.write_bytes(payload)
    dest = tmp_path / "viewer_drop" / "from_host.bin"

    viewer_completes = []
    host = _start_host()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
        )
        viewer.set_file_receiver(FileReceiver(
            on_complete=lambda *args: viewer_completes.append(args),
        ))
        viewer.connect(timeout=2.0)
        assert _wait_until(lambda: host.connected_clients == 1)
        host.send_file_to_viewers(str(src), str(dest))
        assert _wait_until(lambda: bool(viewer_completes), timeout=5.0)
        _tid, ok, err, written_path = viewer_completes[-1]
        assert ok is True
        assert err is None
        assert Path(written_path) == dest
        assert dest.read_bytes() == payload
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_send_file_when_viewer_not_connected():
    viewer = RemoteDesktopViewer(host="127.0.0.1", port=1, token="t")
    with pytest.raises(ConnectionError):
        viewer.send_file("anything", "anywhere")
