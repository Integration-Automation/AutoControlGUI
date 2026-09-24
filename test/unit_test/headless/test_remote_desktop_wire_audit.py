"""Remote-desktop wire and storage defects from the 2026-09-24 audit (local sockets and fakes only).

A non-ASCII Sec-WebSocket-Key killed the handshake thread; a client answered
PINGs unmasked, a server took unmasked frames and oversized control frames;
a dest_path naming no file raised past the receiver; a failed first frame
left the encrypted recorder's count ahead of its entries; a tampered manifest
raised instead of failing verification; a mic whose device failed to start
could never start again.
"""
import json
import socket
import struct
import uuid

import pytest

from je_auto_control.utils.remote_desktop import ws_protocol
from je_auto_control.utils.remote_desktop.file_transfer import FileReceiver, encode_begin
from je_auto_control.utils.remote_desktop.jpeg_recorder_encrypted import (
    EncryptedJpegSequenceRecorder, verify_manifest,
)
from je_auto_control.utils.remote_desktop.ws_protocol import WsProtocolError


def _frame(opcode, payload, mask_key=None):
    header = bytes([0x80 | opcode])
    length = len(payload)
    mask_bit = 0x80 if mask_key else 0
    if length < 126:
        header += bytes([mask_bit | length])
    else:
        header += bytes([mask_bit | 126]) + struct.pack("!H", length)
    if mask_key:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        header += mask_key
    return header + payload


@pytest.fixture()
def pair():
    left, right = socket.socketpair()
    left.settimeout(5)
    right.settimeout(5)
    yield left, right
    left.close()
    right.close()


def test_a_non_ascii_key_is_a_protocol_error(pair):
    server, client = pair
    client.sendall(("GET / HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                    "Sec-WebSocket-Key: " + chr(0xE9) + "abc\r\n\r\n").encode("latin-1"))
    with pytest.raises(WsProtocolError):
        ws_protocol.server_handshake(server)


def test_a_client_answers_a_ping_masked(pair):
    client, server = pair
    server.sendall(_frame(ws_protocol.OPCODE_PING, b"hi") + _frame(ws_protocol.OPCODE_BINARY, b"x"))
    assert ws_protocol.recv_message(client, mask=True, expect_masked=False) == b"x"
    pong = server.recv(64)
    assert pong[0] & 0x0F == ws_protocol.OPCODE_PONG and pong[1] & 0x80


def test_a_server_refuses_unmasked_and_oversized_control_frames(pair):
    server, client = pair
    client.sendall(_frame(ws_protocol.OPCODE_BINARY, b"x"))
    with pytest.raises(WsProtocolError):
        ws_protocol.recv_message(server, expect_masked=True)
    client.sendall(_frame(ws_protocol.OPCODE_PING, b"p" * 200, mask_key=b"\x01\x02\x03\x04"))
    with pytest.raises(WsProtocolError):
        ws_protocol.recv_message(server, expect_masked=True)


@pytest.mark.parametrize("dest", [".", "/"])
def test_a_destination_naming_no_file_fails_the_transfer(dest):
    finished = []
    receiver = FileReceiver(on_complete=lambda *args: finished.append(args))
    receiver.handle_begin(encode_begin(str(uuid.uuid4()), dest, 3))
    assert finished and finished[0][1] is False


def test_a_boolean_size_is_refused():
    from je_auto_control.utils.remote_desktop.file_transfer import FileTransferError, decode_begin
    payload = json.dumps({"transfer_id": str(uuid.uuid4()), "dest_path": "x", "size": True}).encode()
    with pytest.raises(FileTransferError):
        decode_begin(payload)


def test_a_failed_first_frame_is_not_counted(tmp_path, monkeypatch):
    recorder = EncryptedJpegSequenceRecorder(str(tmp_path / "rec"))
    recorder.start()
    real_write = type(tmp_path).write_bytes
    calls = []

    def flaky(self, data):
        calls.append(self.name)
        if len(calls) == 1:
            raise OSError("disk full")
        return real_write(self, data)

    monkeypatch.setattr(type(tmp_path), "write_bytes", flaky)
    recorder.record_frame(b"one")
    recorder.record_frame(b"two")
    monkeypatch.undo()
    manifest = json.loads(recorder.stop().read_text(encoding="utf-8"))
    assert manifest["frame_count"] == len(manifest["entries"]) == 1


@pytest.mark.parametrize("content", ['{"signature_hmac_sha256": "a"}', "[1]", "{not json"])
def test_a_malformed_manifest_does_not_verify(tmp_path, content):
    path = tmp_path / "manifest.json"
    path.write_text(content, encoding="utf-8")
    assert verify_manifest(path, b"k" * 32) is False


def test_a_mic_that_failed_to_start_can_start_again(monkeypatch):
    pytest.importorskip("aiortc")
    from je_auto_control.utils.remote_desktop import webrtc_mic
    attempts = []

    class _Capture:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            attempts.append(True)
            if len(attempts) == 1:
                raise webrtc_mic.AudioBackendError("device busy")

        def stop(self):
            pass

    monkeypatch.setattr(webrtc_mic, "AudioCapture", _Capture)
    monkeypatch.setattr(webrtc_mic, "is_audio_backend_available", lambda: True)
    sender = webrtc_mic.MicUplinkSender(object())
    with pytest.raises(webrtc_mic.AudioBackendError):
        sender.start()
    sender.start()
    assert len(attempts) == 2
