"""The signing key is kept apart from the right to execute. No Qt.

``AC_sign_action_file`` signed with the per-user HMAC key, and verification
read that same key -- so whoever could run an action through the socket, REST
or MCP could sign a file first and then run it, and
``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS`` only stopped someone who could write
files but not execute. Version-2 signatures are Ed25519: the execution endpoint
holds the public key alone, which verifies and cannot sign.
"""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

pytest.importorskip("cryptography")

from je_auto_control.utils.action_signing import (  # noqa: E402  # reason: after importorskip
    SigningConfig, action_signing_config, create_signing_keypair,
    sign_action_file, verify_action_file,
)
from je_auto_control.utils.action_signing import signer  # noqa: E402  # reason: after importorskip
from je_auto_control.utils.exception.exceptions import (  # noqa: E402  # reason: after importorskip
    AutoControlException, CryptographyUnavailableError,
)
from je_auto_control.utils.json import json_file  # noqa: E402  # reason: after importorskip

PRIVATE_ENV = "JE_AUTOCONTROL_ACTION_SIGNING_PRIVATE_KEY"
PUBLIC_ENV = "JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY"
LEGACY_ENV = "JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES"
REQUIRE_ENV = "JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS"
_HMAC_KEY = b"h" * 32


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch, tmp_path):
    """No signing variable leaks in, and the per-user key lives in tmp_path."""
    for name in (PRIVATE_ENV, PUBLIC_ENV, LEGACY_ENV, REQUIRE_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(signer, "_default_key_path",
                        lambda: tmp_path / "home" / "action_signing_key")


@pytest.fixture
def keys(tmp_path):
    """A key pair as the signing machine would create it."""
    private, public = tmp_path / "signer" / "private.pem", tmp_path / "public.pem"
    create_signing_keypair(private, public)
    return private, public


@pytest.fixture
def execution_endpoint(monkeypatch, keys):
    """An endpoint that enforces signatures and holds the public key only."""
    monkeypatch.setenv(PUBLIC_ENV, str(keys[1]))
    monkeypatch.setenv(REQUIRE_ENV, "1")
    return keys


def _script(tmp_path, name="flow.json"):
    path = tmp_path / name
    path.write_text(json.dumps([["AC_noop"]]), encoding="utf-8")
    return path


# --- the key pair -------------------------------------------------------------

def test_a_key_pair_is_two_pem_files_and_the_private_one_is_private(keys):
    private, public = keys
    assert b"PRIVATE KEY" in private.read_bytes()
    assert b"PUBLIC KEY" in public.read_bytes()
    assert b"PRIVATE" not in public.read_bytes()
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(private).st_mode) == 0o600


@pytest.mark.parametrize("existing", ["private", "public"])
def test_an_existing_key_is_never_overwritten(tmp_path, existing):
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    (private if existing == "private" else public).write_bytes(b"keep me")
    with pytest.raises(AutoControlException, match="already exists"):
        create_signing_keypair(private, public)
    survivor = private if existing == "private" else public
    assert survivor.read_bytes() == b"keep me"
    assert not (public if existing == "private" else private).exists()


# --- version-2 signatures -------------------------------------------------------

def test_a_version_2_signature_verifies_with_the_public_key_alone(tmp_path, keys):
    private, public = keys
    path = _script(tmp_path)
    sidecar = sign_action_file(path, private_key_path=private)
    envelope = json.loads(Path(sidecar).read_text(encoding="utf-8"))
    assert envelope["version"] == 2
    assert envelope["algorithm"] == "ed25519"
    private.unlink()  # the verifier never has it
    assert verify_action_file(path, public_key_path=public).verified is True


def test_a_tampered_file_fails_version_2_verification(tmp_path, keys):
    private, public = keys
    path = _script(tmp_path)
    sign_action_file(path, private_key_path=private)
    path.write_text('[["AC_evil"]]', encoding="utf-8")
    result = verify_action_file(path, public_key_path=public)
    assert result.verified is False
    assert "mismatch" in result.reason


def test_a_signature_from_another_key_pair_is_refused(tmp_path, keys):
    other_private, other_public = tmp_path / "o.pem", tmp_path / "o.pub"
    create_signing_keypair(other_private, other_public)
    path = _script(tmp_path)
    sign_action_file(path, private_key_path=other_private)
    result = verify_action_file(path, public_key_path=keys[1])
    assert result.verified is False
    assert "different key" in result.reason


@pytest.mark.parametrize("sidecar", [
    "{not json", '{"version": 3, "algorithm": "ed25519", "signature": "AAAA"}',
    '{"version": 2, "algorithm": "none", "signature": "AAAA"}',
    '{"version": 2, "algorithm": "ed25519", "signature": "***"}',
    '{"version": 2, "algorithm": "ed25519"}',
])
def test_a_malformed_envelope_is_unverified_not_a_crash(tmp_path, keys, sidecar):
    path = _script(tmp_path)
    Path(str(path) + ".sig").write_text(sidecar, encoding="utf-8")
    assert verify_action_file(path, public_key_path=keys[1]).verified is False


def test_a_version_2_signature_without_a_public_key_is_unverified(tmp_path, keys):
    path = _script(tmp_path)
    sign_action_file(path, private_key_path=keys[0])
    result = verify_action_file(path)
    assert result.verified is False
    assert PUBLIC_ENV in result.reason


def test_the_signing_machine_signs_from_its_environment(tmp_path, keys, monkeypatch):
    monkeypatch.setenv(PRIVATE_ENV, str(keys[0]))
    path = _script(tmp_path)
    sidecar = sign_action_file(path)
    assert json.loads(Path(sidecar).read_text(encoding="utf-8"))["version"] == 2
    assert verify_action_file(path).verified is True  # public half derived


# --- the execution endpoint -----------------------------------------------------

def test_verifier_has_no_private_key(execution_endpoint):
    verifier = action_signing_config()
    assert isinstance(verifier, SigningConfig)
    assert verifier.private_key_path is None
    assert verifier.public_key_path == execution_endpoint[1]
    assert verifier.verify_only is True


def test_execution_endpoint_cannot_sign(tmp_path, execution_endpoint):
    from je_auto_control.utils.executor.action_executor import executor
    path = _script(tmp_path)
    for arguments in ({"path": str(path)}, {"path": str(path), "key": "anything"}):
        with pytest.raises(AutoControlException, match="verifies only"):
            executor.event_dict["AC_sign_action_file"](**arguments)
    assert not Path(str(path) + ".sig").exists()
    assert not (tmp_path / "home" / "action_signing_key").exists(), \
        "the refusal must not fall back to creating a personal key"


def test_execution_endpoint_cannot_mint_a_key_pair(tmp_path, execution_endpoint):
    from je_auto_control.utils.executor.action_executor import executor
    with pytest.raises(AutoControlException, match="verifies only"):
        executor.event_dict["AC_create_signing_keypair"](
            private_path=str(tmp_path / "p.pem"), public_path=str(tmp_path / "p.pub"))
    assert not (tmp_path / "p.pem").exists()


def test_execution_endpoint_runs_a_file_signed_elsewhere(tmp_path, execution_endpoint):
    path = _script(tmp_path)
    sign_action_file(path, private_key_path=execution_endpoint[0])
    assert json_file.read_executable_action_json(str(path)) == [["AC_noop"]]


def test_legacy_signature_requires_explicit_migration(tmp_path, execution_endpoint, monkeypatch):
    path = _script(tmp_path)
    monkeypatch.delenv(PUBLIC_ENV)
    sign_action_file(path)  # the per-user HMAC key, as before version 2
    monkeypatch.setenv(PUBLIC_ENV, str(execution_endpoint[1]))
    with pytest.raises(AutoControlException, match="legacy HMAC"):
        json_file.read_executable_action_json(str(path))
    monkeypatch.setenv(LEGACY_ENV, "1")
    assert json_file.read_executable_action_json(str(path)) == [["AC_noop"]]


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_migration_mode_is_off_unless_switched_on(monkeypatch, value):
    monkeypatch.setenv(LEGACY_ENV, value)
    assert action_signing_config().accept_legacy is False


def test_an_explicit_hmac_key_does_not_bypass_version_2(tmp_path, execution_endpoint, monkeypatch):
    path = _script(tmp_path)
    monkeypatch.delenv(PUBLIC_ENV)
    sign_action_file(path, _HMAC_KEY)
    monkeypatch.setenv(PUBLIC_ENV, str(execution_endpoint[1]))
    assert verify_action_file(path, _HMAC_KEY).verified is False


# --- deployments that never configured a key pair -------------------------------

def test_without_a_key_pair_signing_is_the_hmac_sidecar_it_always_was(tmp_path, monkeypatch):
    path = _script(tmp_path)
    sidecar = Path(sign_action_file(path))
    assert len(sidecar.read_text(encoding="utf-8")) == 64  # bare hex HMAC-SHA256
    monkeypatch.setenv(REQUIRE_ENV, "1")
    assert json_file.read_executable_action_json(str(path)) == [["AC_noop"]]


# --- surfaces -------------------------------------------------------------------

def test_the_executor_commands_cover_the_whole_flow(tmp_path):
    from je_auto_control.utils.executor.action_executor import executor
    private, public = tmp_path / "k.pem", tmp_path / "k.pub"
    path = _script(tmp_path)
    created = executor.event_dict["AC_create_signing_keypair"](
        private_path=str(private), public_path=str(public))
    assert created == {"private_path": str(private), "public_path": str(public)}
    executor.event_dict["AC_sign_action_file"](path=str(path), private_key_path=str(private))
    verified = executor.event_dict["AC_verify_action_file"](
        path=str(path), public_key_path=str(public))
    assert verified["verified"] is True


def test_the_facade_and_the_script_builder_expose_the_key_pair_command():
    import je_auto_control
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    for name in ("create_signing_keypair", "action_signing_config", "SigningConfig",
                 "CryptographyUnavailableError"):
        assert name in je_auto_control.__all__ and hasattr(je_auto_control, name)
    specs = {spec.command: spec for spec in _build_specs()}
    assert [field.name for field in specs["AC_create_signing_keypair"].fields] == [
        "private_path", "public_path"]
    assert "private_key_path" in [f.name for f in specs["AC_sign_action_file"].fields]
    assert "public_key_path" in [f.name for f in specs["AC_verify_action_file"].fields]


# --- a platform without the cryptography wheel ----------------------------------

def test_a_missing_cryptography_wheel_is_a_typed_error_with_an_install_hint(
        tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "cryptography.exceptions", None)
    with pytest.raises(CryptographyUnavailableError) as caught:
        create_signing_keypair(tmp_path / "a.pem", tmp_path / "a.pub")
    assert isinstance(caught.value, AutoControlException)
    assert isinstance(caught.value, RuntimeError)
    assert "pip install cryptography" in str(caught.value)
    assert "Windows arm64" in str(caught.value)
    assert not (tmp_path / "a.pem").exists()


def test_hmac_signing_still_works_without_cryptography(tmp_path, monkeypatch):
    for name in [m for m in sys.modules if m.split(".")[0] == "cryptography"]:
        monkeypatch.setitem(sys.modules, name, None)
    path = _script(tmp_path)
    sign_action_file(path, _HMAC_KEY)
    assert verify_action_file(path, _HMAC_KEY).verified is True
