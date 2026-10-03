"""Ed25519 action signatures: private signing keys stay off execution hosts.

Version-2 JSON sidecars authenticate exact file bytes with a domain prefix.
Keys must be configured explicitly; verification never creates or reads a
private key. Legacy HMAC sidecars require an explicit migration opt-in.
Crypto imports are lazy so unsupported platforms can still import the facade.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING, Union

from je_auto_control.utils.action_signing._key_file import load_or_create_key_file
from je_auto_control.utils.exception.exceptions import AutoControlException, CryptoUnavailableError
from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )

_REQUIRE_ENV = "JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS"
_PRIVATE_ENV = "JE_AUTOCONTROL_SIGNING_PRIVATE_KEY"
_PUBLIC_ENV = "JE_AUTOCONTROL_SIGNING_PUBLIC_KEY"
_LEGACY_ENV = "JE_AUTOCONTROL_ALLOW_LEGACY_HMAC"
_LEGACY_KEY_ENV = "JE_AUTOCONTROL_LEGACY_SIGNING_KEY"
_DOMAIN = b"je_auto_control.action-signature.v2\x00"
KeyType = Optional[Union[bytes, str]]
KeyPath = Optional[Union[str, Path]]


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of verifying exact action-file bytes against a trusted key."""
    path: str
    verified: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Return the result in a JSON-compatible form."""
        return asdict(self)


def _key_material(key: KeyType, path: KeyPath, environment: str, role: str) -> bytes:
    if key is not None:
        raw = key if isinstance(key, bytes) else key.encode("utf-8")
        if not raw:
            raise AutoControlException(f"an empty {role} key is invalid")
        return raw
    configured = path if path is not None else os.environ.get(environment)
    if not configured:
        raise AutoControlException(
            f"no {role} key configured; set {environment} or supply a key path")
    return Path(configured).read_bytes()


def _load_private(key: KeyType = None, path: KeyPath = None) -> Ed25519PrivateKey:
    raw = _key_material(key, path, _PRIVATE_ENV, "private")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        loaded = (Ed25519PrivateKey.from_private_bytes(raw) if len(raw) == 32
                  else serialization.load_pem_private_key(raw, password=None))
        if not isinstance(loaded, Ed25519PrivateKey):
            raise ValueError("expected Ed25519")
        return loaded
    except ImportError as error:
        raise CryptoUnavailableError(
            'Ed25519 private keys require: pip install "cryptography>=50.0.0"') from error
    except (ValueError, TypeError) as error:
        raise AutoControlException(
            "Ed25519 private key unavailable or invalid; install cryptography") from error


def _load_public(key: KeyType = None, path: KeyPath = None) -> Ed25519PublicKey:
    raw = _key_material(key, path, _PUBLIC_ENV, "public")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        loaded = (Ed25519PublicKey.from_public_bytes(raw) if len(raw) == 32
                  else serialization.load_pem_public_key(raw))
        if not isinstance(loaded, Ed25519PublicKey):
            raise ValueError("expected Ed25519")
        return loaded
    except ImportError as error:
        raise CryptoUnavailableError(
            'Ed25519 public keys require: pip install "cryptography>=50.0.0"') from error
    except (ValueError, TypeError) as error:
        raise AutoControlException(
            "Ed25519 public key unavailable or invalid; install cryptography") from error


def create_signing_keypair(private_path: Path, public_path: Path) -> None:
    """Create private/public PEM files without overwriting existing key material.

    Both files are created with mode 0600. Distribute only the public file to
    execution hosts. Repeated creation verifies that the existing pair matches.
    """
    private_path, public_path = Path(private_path), Path(public_path)
    if private_path.resolve() == public_path.resolve():
        raise AutoControlException("private and public key paths must differ")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as error:
        raise CryptoUnavailableError(
            'Ed25519 key generation requires: pip install "cryptography>=50.0.0"') from error
    generated = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    )
    material = load_or_create_key_file(private_path, lambda: generated, 64)
    private = _load_private(material)
    expected = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    actual = load_or_create_key_file(public_path, lambda: expected, 64)
    if actual != expected:
        raise AutoControlException(
            "existing public key does not match the private key; neither was overwritten")


def _sig_path(path: Union[str, Path]) -> Path:
    target = Path(path)
    return target.with_name(target.name + ".sig")


def _legacy_key(key: KeyType) -> bytes:
    """Read only an explicitly supplied legacy key; never create one."""
    return _key_material(key, os.environ.get(_LEGACY_KEY_ENV), _LEGACY_KEY_ENV, "legacy HMAC")


def sign_action_file(path: Union[str, Path], key: KeyType = None, *,
                     private_key_path: KeyPath = None, legacy_hmac: bool = False) -> str:
    """Sign exact file bytes with a configured private key; return the sidecar path.

    ``key`` accepts 32 raw bytes or PEM material. Legacy HMAC signing requires
    both ``legacy_hmac=True`` and explicit ``key`` material.
    """
    data = Path(path).read_bytes()
    if legacy_hmac:
        if key is None:
            raise AutoControlException("legacy signing requires explicit key material")
        envelope = {"version": 1, "algorithm": "HMAC-SHA256",
                    "signature": hmac.new(_legacy_key(key), data, hashlib.sha256).hexdigest()}
    else:
        private = _load_private(key, private_key_path)
        envelope = {"version": 2, "algorithm": "Ed25519",
                    "key_id": hashlib.sha256(private.public_key().public_bytes_raw()).hexdigest(),
                    "signature": base64.b64encode(private.sign(_DOMAIN + data)).decode("ascii")}
    destination = _sig_path(path)
    atomic_write_text(destination, json.dumps(envelope, sort_keys=True), encoding="utf-8")
    autocontrol_logger.info("signed action file %s", path)
    return str(destination)


def _verify_ed25519(data: bytes, envelope: Dict[str, Any], key: KeyType, path: KeyPath) -> bool:
    from cryptography.exceptions import InvalidSignature
    public = _load_public(key, path)
    if envelope.get("key_id") != hashlib.sha256(public.public_bytes_raw()).hexdigest():
        return False
    try:
        signature = base64.b64decode(envelope["signature"], validate=True)
        public.verify(signature, _DOMAIN + data)
    except (InvalidSignature, ValueError, TypeError, KeyError):
        return False
    return True


def _verify_legacy(data: bytes, envelope: Dict[str, Any], key: KeyType) -> bool:
    actual = hmac.new(_legacy_key(key), data, hashlib.sha256).hexdigest()
    expected = envelope.get('signature')
    return isinstance(expected, str) and hmac.compare_digest(
        expected.encode('utf-8'), actual.encode())


def _check_envelope(data: bytes, envelope: Any, key: KeyType, public_key_path: KeyPath,
                     allow_legacy_hmac: bool) -> Optional[str]:
    if not isinstance(envelope, dict):
        return 'invalid signature envelope'
    version, algorithm = envelope.get('version'), envelope.get('algorithm')
    if isinstance(version, bool) or not isinstance(version, int):
        return 'invalid signature envelope'
    if version == 2 and algorithm == 'Ed25519':
        valid = _verify_ed25519(data, envelope, key, public_key_path)
    elif version == 1 and algorithm == 'HMAC-SHA256':
        if not allow_legacy_hmac:
            return 'legacy HMAC signature requires explicit migration opt-in'
        valid = _verify_legacy(data, envelope, key)
    else:
        return 'unsupported signature version or algorithm'
    return None if valid else 'signature mismatch (tampered or wrong key)'


def _verify_bytes(path: Union[str, Path], data: bytes, key: KeyType,
                  raise_on_fail: bool, public_key_path: KeyPath = None,
                  allow_legacy_hmac: bool = False) -> VerifyResult:
    try:
        raw = _sig_path(path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return _fail(path, "missing signature sidecar", raise_on_fail)
    except (OSError, UnicodeDecodeError) as error:
        return _fail(path, f"read error: {error}", raise_on_fail)
    try:
        try:
            envelope = json.loads(raw)
        except ValueError:
            envelope = {"version": 1, "algorithm": "HMAC-SHA256", "signature": raw}
        reason = _check_envelope(data, envelope, key, public_key_path, allow_legacy_hmac)
    except (OSError, AutoControlException, ImportError, ValueError, TypeError) as error:
        return _fail(path, f"verification unavailable: {error}", raise_on_fail)
    if reason is not None:
        return _fail(path, reason, raise_on_fail)
    return VerifyResult(str(path), True, "signature valid")


def verify_action_file(path: Union[str, Path], key: KeyType = None, *,
                       raise_on_fail: bool = False, public_key_path: KeyPath = None,
                       allow_legacy_hmac: bool = False) -> VerifyResult:
    """Verify using a public key only; reject legacy HMAC unless explicitly allowed."""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        return _fail(path, f"read error: {error}", raise_on_fail)
    return _verify_bytes(path, data, key, raise_on_fail, public_key_path, allow_legacy_hmac)


def _fail(path: Union[str, Path], reason: str, raise_on_fail: bool) -> VerifyResult:
    if raise_on_fail:
        raise AutoControlException(f"action file {path!r} failed verification: {reason}")
    autocontrol_logger.info("action file %r unverified: %s", path, reason)
    return VerifyResult(str(path), False, reason)


def signing_required() -> bool:
    """Whether signed-file enforcement is enabled, read for every operation."""
    return bool(os.environ.get(_REQUIRE_ENV))


def _legacy_enabled() -> bool:
    return os.environ.get(_LEGACY_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def require_signed_actions(path: Union[str, Path], key: KeyType = None) -> None:
    """Verify configured public signatures when signed-file enforcement is enabled."""
    if signing_required():
        verify_action_file(path, key, raise_on_fail=True, allow_legacy_hmac=_legacy_enabled())


def read_signed_action_bytes(path: Union[str, Path], key: KeyType = None) -> bytes:
    """Read once and verify those exact bytes when enforcement is enabled."""
    data = Path(path).read_bytes()
    if signing_required():
        _verify_bytes(path, data, key, raise_on_fail=True, allow_legacy_hmac=_legacy_enabled())
    return data
