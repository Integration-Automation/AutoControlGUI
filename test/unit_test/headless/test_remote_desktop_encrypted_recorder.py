"""Phase 6.2: tests for the AES-GCM encrypted JPEG recorder."""
import json
import secrets

import pytest

from je_auto_control.utils.remote_desktop.jpeg_recorder_encrypted import (
    EncryptedJpegSequenceRecorder, decrypt_frame,
    derive_key_from_passphrase, generate_session_key, verify_manifest,
)


def test_records_and_decrypts_three_frames(tmp_path):
    rec = EncryptedJpegSequenceRecorder(str(tmp_path / "enc"))
    rec.start()
    payloads = [b"jpeg-1", b"jpeg-2", b"jpeg-3"]
    for p in payloads:
        rec.record_frame(p)
    manifest_path = rec.stop()
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert raw["encrypted"] is True
    assert raw["algorithm"] == "AES-256-GCM"
    assert raw["frame_count"] == 3
    # Round-trip every frame.
    for original, entry in zip(payloads, raw["entries"]):
        ciphertext = (manifest_path.parent / entry["filename"]).read_bytes()
        decrypted = decrypt_frame(ciphertext, rec.session_key)
        assert decrypted == original


def test_manifest_signature_verifies(tmp_path):
    rec = EncryptedJpegSequenceRecorder(str(tmp_path / "enc"))
    rec.start()
    rec.record_frame(b"hello")
    manifest = rec.stop()
    assert verify_manifest(manifest, rec.hmac_key) is True


def test_manifest_signature_rejects_tampered_data(tmp_path):
    rec = EncryptedJpegSequenceRecorder(str(tmp_path / "enc"))
    rec.start()
    rec.record_frame(b"hello")
    manifest = rec.stop()
    # Flip a byte in frame_count.
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["frame_count"] = 999
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    assert verify_manifest(manifest, rec.hmac_key) is False


def test_wrong_hmac_key_rejects(tmp_path):
    rec = EncryptedJpegSequenceRecorder(str(tmp_path / "enc"))
    rec.start()
    rec.record_frame(b"x")
    manifest = rec.stop()
    assert verify_manifest(manifest, secrets.token_bytes(32)) is False


def test_decrypt_with_wrong_key_raises(tmp_path):
    rec = EncryptedJpegSequenceRecorder(str(tmp_path / "enc"))
    rec.start()
    rec.record_frame(b"sensitive payload")
    manifest_path = rec.stop()
    entry_name = json.loads(
        manifest_path.read_text(encoding="utf-8"),
    )["entries"][0]["filename"]
    ciphertext = (manifest_path.parent / entry_name).read_bytes()
    from cryptography.exceptions import InvalidTag
    with pytest.raises(InvalidTag):
        decrypt_frame(ciphertext, secrets.token_bytes(32))


def test_explicit_session_key_round_trip(tmp_path):
    key = generate_session_key()
    rec = EncryptedJpegSequenceRecorder(
        str(tmp_path / "enc"), session_key=key,
    )
    rec.start()
    rec.record_frame(b"frame-with-explicit-key")
    manifest_path = rec.stop()
    entry = json.loads(
        manifest_path.read_text(encoding="utf-8"),
    )["entries"][0]
    ciphertext = (manifest_path.parent / entry["filename"]).read_bytes()
    assert decrypt_frame(ciphertext, key) == b"frame-with-explicit-key"


def test_bad_session_key_size_raises(tmp_path):
    with pytest.raises(ValueError):
        EncryptedJpegSequenceRecorder(
            str(tmp_path / "enc"), session_key=b"short",
        )


def test_derive_key_from_passphrase_deterministic():
    salt = secrets.token_bytes(16)
    k1 = derive_key_from_passphrase("hunter2", salt)
    k2 = derive_key_from_passphrase("hunter2", salt)
    assert k1 == k2
    k3 = derive_key_from_passphrase("hunter3", salt)
    assert k1 != k3
    assert len(k1) == 32


def test_derive_key_validates_inputs():
    with pytest.raises(ValueError):
        derive_key_from_passphrase("", secrets.token_bytes(16))
    with pytest.raises(ValueError):
        derive_key_from_passphrase("pass", b"too-short")


def test_record_after_stop_ignored(tmp_path):
    rec = EncryptedJpegSequenceRecorder(str(tmp_path / "enc"))
    rec.start()
    rec.record_frame(b"first")
    rec.stop()
    rec.record_frame(b"second-should-be-dropped")
    assert rec.frame_count == 1


def test_non_bytes_payload_dropped(tmp_path):
    rec = EncryptedJpegSequenceRecorder(str(tmp_path / "enc"))
    rec.start()
    rec.record_frame("not-bytes")  # type: ignore[arg-type]  # NOSONAR python:S5655  # reason: intentional bad-type negative test
    rec.record_frame(None)  # type: ignore[arg-type]  # NOSONAR python:S5655  # reason: intentional bad-type negative test
    assert rec.frame_count == 0
