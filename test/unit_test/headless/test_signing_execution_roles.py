"""An execution host verifies public signatures without possessing signing keys."""
import hashlib
import hmac
import json
from pathlib import Path

import pytest

from je_auto_control.utils.action_signing import signer
from je_auto_control.utils.exception.exceptions import AutoControlException


def _script(tmp_path):
    path = tmp_path / "flow.json"
    path.write_text('[["AC_set_var", {"name": "x", "value": 1}]]', encoding="utf-8")
    return path


def test_verifier_has_no_private_key(tmp_path, monkeypatch):
    private = tmp_path / "signer" / "private.pem"
    public = tmp_path / "executor" / "public.pem"
    signer.create_signing_keypair(private, public)
    path = _script(tmp_path)
    signer.sign_action_file(path, private_key_path=private)
    private.unlink()
    monkeypatch.setenv("JE_AUTOCONTROL_SIGNING_PUBLIC_KEY", str(public))
    monkeypatch.delenv("JE_AUTOCONTROL_SIGNING_PRIVATE_KEY", raising=False)
    assert signer.verify_action_file(path).verified is True
    envelope = json.loads(Path(str(path) + ".sig").read_text(encoding="utf-8"))
    assert envelope["version"] == 2
    assert envelope["algorithm"] == "Ed25519"


def test_execution_endpoint_cannot_sign(tmp_path, monkeypatch):
    from je_auto_control.utils.executor.action_executor import _sign_action_file
    monkeypatch.delenv("JE_AUTOCONTROL_SIGNING_PRIVATE_KEY", raising=False)
    with pytest.raises(AutoControlException, match="private key"):
        _sign_action_file(str(_script(tmp_path)))


def test_legacy_signature_requires_explicit_migration(tmp_path):
    path = _script(tmp_path)
    key = b"legacy-migration-key"
    Path(str(path) + ".sig").write_text(hmac.new(key, path.read_bytes(), hashlib.sha256).hexdigest())
    assert signer.verify_action_file(path, key).verified is False
    assert signer.verify_action_file(path, key, allow_legacy_hmac=True).verified is True


def test_wrong_public_key_and_tampering_are_rejected(tmp_path):
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    signer.create_signing_keypair(private, public)
    other_private, other_public = tmp_path / "other-private.pem", tmp_path / "other-public.pem"
    signer.create_signing_keypair(other_private, other_public)
    path = _script(tmp_path)
    signer.sign_action_file(path, private_key_path=private)
    assert not signer.verify_action_file(path, public_key_path=other_public).verified
    path.write_bytes(b"[]")
    assert not signer.verify_action_file(path, public_key_path=public).verified


def test_keypair_creation_is_idempotent_and_refuses_mismatched_public_key(tmp_path):
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    signer.create_signing_keypair(private, public)
    original = private.read_bytes(), public.read_bytes()
    signer.create_signing_keypair(private, public)
    assert (private.read_bytes(), public.read_bytes()) == original
    public.write_bytes(b"x" * 128)
    with pytest.raises(AutoControlException):
        signer.create_signing_keypair(private, public)
    assert private.read_bytes() == original[0]


def test_verification_does_not_create_any_default_key(tmp_path, monkeypatch):
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    signer.create_signing_keypair(private, public)
    path = _script(tmp_path)
    signer.sign_action_file(path, private_key_path=private)
    home = tmp_path / "empty-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("JE_AUTOCONTROL_SIGNING_PUBLIC_KEY", raising=False)
    assert not signer.verify_action_file(path).verified
    assert list(home.rglob("*")) == []


def test_signing_and_verification_cli_use_separate_keys(tmp_path, capsys):
    from je_auto_control.cli import main
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    assert main(["signing-keygen", "--private-key", str(private), "--public-key", str(public)]) == 0
    path = _script(tmp_path)
    assert main(["sign", str(path), "--private-key", str(private)]) == 0
    assert main(["verify", str(path), "--public-key", str(public)]) == 0
    path.write_text("[]", encoding="utf-8")
    assert main(["verify", str(path), "--public-key", str(public)]) == 1
    capsys.readouterr()


def test_signing_surfaces_use_public_and_private_paths(tmp_path):
    import je_auto_control as ac
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    private, public = tmp_path / 'private.pem', tmp_path / 'public.pem'
    ac.create_signing_keypair(private, public)
    path = _script(tmp_path)
    executor.execute_action([['AC_sign_action_file', {
        'path': str(path), 'private_key_path': str(private)}]])
    assert ac.verify_action_file(path, public_key_path=public).verified
    tools = {tool.name: tool for tool in build_default_tool_registry(aliases=False)}
    assert tools['ac_verify_action_file'].invoke({
        'path': str(path), 'public_key_path': str(public)})['verified']
    assert not tools['ac_sign_action_file'].annotations.read_only
    assert tools['ac_verify_action_file'].annotations.read_only
    assert 'AC_create_signing_keypair' in executor.known_commands()


def test_failed_key_generation_leaves_no_empty_file(tmp_path):
    from je_auto_control.utils.action_signing._key_file import load_or_create_key_file
    path = tmp_path / 'key'
    def fail():
        raise RuntimeError('generator failed')
    with pytest.raises(RuntimeError):
        load_or_create_key_file(path, fail, 32)
    assert not path.exists()


def test_boolean_version_is_not_a_legacy_envelope(tmp_path):
    path = _script(tmp_path)
    key = b'legacy-key'
    Path(str(path) + '.sig').write_text(json.dumps({
        'version': True, 'algorithm': 'HMAC-SHA256',
        'signature': hmac.new(key, path.read_bytes(), hashlib.sha256).hexdigest()}))
    assert not signer.verify_action_file(path, key, allow_legacy_hmac=True).verified
