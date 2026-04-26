"""Tests for the remote_desktop wire protocol and auth helpers."""
import pytest

from je_auto_control.utils.remote_desktop import auth
from je_auto_control.utils.remote_desktop.protocol import (
    HEADER_SIZE, MAX_PAYLOAD_BYTES, MessageType, ProtocolError,
    decode_frame_header, encode_frame,
)


def test_encode_round_trips_through_decode_header():
    payload = b"hello"
    frame = encode_frame(MessageType.AUTH_OK, payload)
    msg_type, length = decode_frame_header(frame[:HEADER_SIZE])
    assert msg_type is MessageType.AUTH_OK
    assert length == len(payload)
    assert frame[HEADER_SIZE:] == payload


def test_decode_rejects_bad_magic():
    bad = b"XX" + bytes([MessageType.FRAME]) + (0).to_bytes(4, "big")
    with pytest.raises(ProtocolError):
        decode_frame_header(bad)


def test_decode_rejects_unknown_type():
    bad = b"AC" + bytes([0xEE]) + (0).to_bytes(4, "big")
    with pytest.raises(ProtocolError):
        decode_frame_header(bad)


def test_decode_rejects_oversized_payload():
    bad = b"AC" + bytes([MessageType.FRAME]) + (MAX_PAYLOAD_BYTES + 1).to_bytes(4, "big")
    with pytest.raises(ProtocolError):
        decode_frame_header(bad)


def test_encode_rejects_oversized_payload():
    with pytest.raises(ProtocolError):
        encode_frame(MessageType.FRAME, b"x" * (MAX_PAYLOAD_BYTES + 1))


def test_encode_requires_bytes_payload():
    with pytest.raises(TypeError):
        encode_frame(MessageType.FRAME, "not bytes")  # type: ignore[arg-type]


def test_compute_response_is_deterministic():
    nonce = bytes(range(auth.NONCE_BYTES))
    a = auth.compute_response("hunter2", nonce)
    b = auth.compute_response("hunter2", nonce)
    assert a == b
    assert len(a) == 32  # SHA-256 digest


def test_compute_response_different_token_diverges():
    nonce = bytes(range(auth.NONCE_BYTES))
    assert auth.compute_response("a", nonce) != auth.compute_response("b", nonce)


def test_verify_response_accepts_correct_hmac():
    nonce = auth.make_nonce()
    response = auth.compute_response("token", nonce)
    assert auth.verify_response("token", nonce, response) is True


def test_verify_response_rejects_wrong_token():
    nonce = auth.make_nonce()
    response = auth.compute_response("token", nonce)
    assert auth.verify_response("other", nonce, response) is False


def test_verify_response_rejects_non_bytes():
    nonce = auth.make_nonce()
    assert auth.verify_response("token", nonce, "not bytes") is False  # type: ignore[arg-type]


def test_make_nonce_has_expected_length():
    assert len(auth.make_nonce()) == auth.NONCE_BYTES
