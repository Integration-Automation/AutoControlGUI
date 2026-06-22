"""Tests for action-file signing (HMAC-SHA256) + encryption (Fernet)."""
from pathlib import Path

import pytest

from je_auto_control.utils.action_signing import (
    decrypt_action_file, encrypt_action_file, require_signed_actions,
    sign_action_file, verify_action_file,
)
from je_auto_control.utils.action_signing.signer import _REQUIRE_ENV
from je_auto_control.utils.exception.exceptions import AutoControlException

_KEY = b"unit-test-key"


def _make(tmp_path, content='[["AC_noop"]]'):
    path = tmp_path / "script.json"
    path.write_text(content, encoding="utf-8")
    return path


def test_sign_then_verify_round_trip(tmp_path):
    path = _make(tmp_path)
    sig = sign_action_file(path, _KEY)
    assert sig.endswith(".sig")
    assert verify_action_file(path, _KEY).verified is True


def test_tampering_is_detected(tmp_path):
    path = _make(tmp_path)
    sign_action_file(path, _KEY)
    path.write_text('[["AC_evil"]]', encoding="utf-8")  # tamper after signing
    result = verify_action_file(path, _KEY)
    assert result.verified is False
    assert "mismatch" in result.reason


def test_wrong_key_fails(tmp_path):
    path = _make(tmp_path)
    sign_action_file(path, _KEY)
    assert verify_action_file(path, b"other-key").verified is False


def test_missing_sidecar_is_unverified(tmp_path):
    path = _make(tmp_path)
    result = verify_action_file(path, _KEY)
    assert result.verified is False
    assert "missing" in result.reason


def test_raise_on_fail_raises(tmp_path):
    path = _make(tmp_path)
    with pytest.raises(AutoControlException):
        verify_action_file(path, _KEY, raise_on_fail=True)


def test_require_signed_actions_is_noop_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv(_REQUIRE_ENV, raising=False)
    path = _make(tmp_path)
    require_signed_actions(path, _KEY)  # enforcement off → no raise


def test_require_signed_actions_enforces_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv(_REQUIRE_ENV, "1")
    path = _make(tmp_path)
    with pytest.raises(AutoControlException):
        require_signed_actions(path, _KEY)
    sign_action_file(path, _KEY)
    require_signed_actions(path, _KEY)  # now signed → no raise


def test_encrypt_then_decrypt_round_trip(tmp_path):
    path = _make(tmp_path)
    original = path.read_bytes()
    enc = encrypt_action_file(path, "pass1")
    assert enc.endswith(".enc")
    assert Path(enc).read_bytes() != original  # ciphertext differs
    out = decrypt_action_file(enc, "pass1")
    assert Path(out).read_bytes() == original


def test_decrypt_with_wrong_key_raises(tmp_path):
    enc = encrypt_action_file(_make(tmp_path), "right")
    with pytest.raises(AutoControlException):
        decrypt_action_file(enc, "wrong")


def test_decrypt_tampered_ciphertext_raises(tmp_path):
    enc = encrypt_action_file(_make(tmp_path), "k")
    Path(enc).write_bytes(b"garbage-not-a-fernet-token")
    with pytest.raises(AutoControlException):
        decrypt_action_file(enc, "k")


def test_decrypt_to_custom_output(tmp_path):
    enc = encrypt_action_file(_make(tmp_path), "k")
    out = tmp_path / "restored.json"
    decrypt_action_file(enc, "k", output_path=str(out))
    assert out.read_text(encoding="utf-8") == '[["AC_noop"]]'
