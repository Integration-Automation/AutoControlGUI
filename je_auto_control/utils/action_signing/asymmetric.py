"""Version-2 action-file signatures: Ed25519, so verifying cannot sign.

The HMAC sidecar is one shared secret -- whoever can check a signature can
write one. Here the signing machine keeps a private key and every execution
endpoint gets the public key, which verifies and nothing else.

A version-2 sidecar is a small JSON envelope::

    {"version": 2, "algorithm": "ed25519", "key_id": "...", "signature": "..."}

``signature`` is base64 of the Ed25519 signature over a fixed context line
followed by the file's exact bytes; ``key_id`` names the public key (the first
16 hex digits of its SHA-256) so a file signed by another pair says so instead
of reading as tampered. Keys are PEM: PKCS#8 for the private half (created
0600), SubjectPublicKeyInfo for the public half. The private half is
encrypted when a passphrase is given at creation; the signer then needs the
same passphrase (an argument, or ``JE_AUTOCONTROL_ACTION_SIGNING_PASSPHRASE``).
A key created without one stays loadable as it is. On Windows, where mode
bits do nothing, the private file is created with an access list naming the
current user only; a private key that other accounts can read -- on either
platform -- is reported with a warning when it is loaded, and still loads.

``cryptography`` is imported lazily -- it has no Windows arm64 wheel, and HMAC
signing must keep working without it. This module is GUI-free and imports no Qt.
"""
import base64
import binascii
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Union

from je_auto_control.utils.action_signing._key_file import write_new_file
from je_auto_control.utils.action_signing._private_file import warn_if_exposed
from je_auto_control.utils.action_signing.config import (
    PASSPHRASE_ENV, action_signing_config, signing_passphrase,
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlException, CryptographyUnavailableError,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

SIGNATURE_VERSION = 2
_ALGORITHM = "ed25519"
_CONTEXT = b"je_auto_control action file signature v2\n"
_KEY_ID_LENGTH = 16

PathLike = Union[str, Path]
Passphrase = Optional[Union[str, bytes]]


def _passphrase_bytes(passphrase: Passphrase) -> Optional[bytes]:
    """``passphrase`` as bytes; ``None`` and the empty string mean "none"."""
    if passphrase is None:
        return None
    raw = passphrase if isinstance(passphrase, bytes) else str(passphrase).encode("utf-8")
    return raw or None


def _ed25519() -> SimpleNamespace:
    """Return the ``cryptography`` names used here, or explain their absence."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as error:
        raise CryptographyUnavailableError(
            "Ed25519 action-file signatures require cryptography "
            "(pip install cryptography). It has no Windows arm64 wheel, so "
            "key-pair signing is unavailable there; HMAC signing still works."
        ) from error
    return SimpleNamespace(
        invalid_signature=InvalidSignature, serialization=serialization,
        private_key=ed25519.Ed25519PrivateKey, public_key=ed25519.Ed25519PublicKey,
    )


def create_signing_keypair(private_path: PathLike, public_path: PathLike,
                           *, passphrase: Passphrase = None) -> None:
    """Create an Ed25519 key pair as two PEM files; neither may exist yet.

    Keep ``private_path`` on the machine that signs and copy ``public_path``
    to every execution endpoint. With ``passphrase`` the private key file is
    encrypted, so the file alone -- a backup, a copied disk -- signs
    nothing; without one it is plain PEM as before. Raises
    :class:`AutoControlException` when a file is already there, or when this
    process is configured to verify only -- a key pair minted on an execution
    endpoint separates nothing.
    """
    if action_signing_config().verify_only:
        raise AutoControlException(
            "this endpoint verifies only (a public key and no private key are "
            "configured); create the key pair on the signing machine",
        )
    private, public = Path(private_path), Path(public_path)
    for target in (private, public):
        if target.exists():
            raise AutoControlException(f"key file {str(target)!r} already exists")
    crypto = _ed25519()
    key = crypto.private_key.generate()
    encoding = crypto.serialization.Encoding.PEM
    secret = _passphrase_bytes(passphrase)
    protection = (crypto.serialization.NoEncryption() if secret is None
                  else crypto.serialization.BestAvailableEncryption(secret))
    write_new_file(private, key.private_bytes(
        encoding, crypto.serialization.PrivateFormat.PKCS8, protection), 0o600)
    try:
        write_new_file(public, key.public_key().public_bytes(
            encoding, crypto.serialization.PublicFormat.SubjectPublicKeyInfo), 0o644)
    except (OSError, AutoControlException):
        private.unlink(missing_ok=True)  # never leave half a pair behind
        raise
    autocontrol_logger.info("created action signing key pair, public half at %s", public)


def _read_key_file(path: Path, kind: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise AutoControlException(
            f"cannot read the {kind} signing key {str(path)!r}: {error}") from error


def _load_private_key(path: PathLike, passphrase: Passphrase = None) -> Any:
    """Load the private key; an encrypted one needs ``passphrase`` or the variable.

    The passphrase is only handed to the loader for a file that says it is
    encrypted: ``cryptography`` refuses a password for a plain key, and a
    signer whose environment carries a passphrase must still load a key that
    was created without one.
    """
    crypto = _ed25519()
    target = Path(path)
    data = _read_key_file(target, "private")
    # Not refused: a key copied in from elsewhere still signs. Said once.
    warn_if_exposed(target, "the private signing key")
    secret: Optional[bytes] = None
    if b"ENCRYPTED" in data:
        secret = _passphrase_bytes(passphrase) or signing_passphrase()
        if secret is None:
            raise AutoControlException(
                f"the private signing key {str(target)!r} is passphrase-protected; "
                f"pass the passphrase or set {PASSPHRASE_ENV}")
    try:
        key = crypto.serialization.load_pem_private_key(data, password=secret)
    except (ValueError, TypeError) as error:
        problem = ("could not be decrypted (wrong passphrase?)" if secret is not None
                   else "is not a PEM private key")
        raise AutoControlException(f"{str(target)!r} {problem}") from error
    if not isinstance(key, crypto.private_key):
        raise AutoControlException(f"{str(target)!r} is not an Ed25519 private key")
    return key


def _load_public_key(path: PathLike) -> Any:
    crypto = _ed25519()
    target = Path(path)
    try:
        key = crypto.serialization.load_pem_public_key(_read_key_file(target, "public"))
    except ValueError as error:
        raise AutoControlException(f"{str(target)!r} is not a PEM public key") from error
    if not isinstance(key, crypto.public_key):
        raise AutoControlException(f"{str(target)!r} is not an Ed25519 public key")
    return key


def _key_id(public_key: Any) -> str:
    crypto = _ed25519()
    raw = public_key.public_bytes(crypto.serialization.Encoding.Raw,
                                  crypto.serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:_KEY_ID_LENGTH]


def sign_envelope(data: bytes, private_key_path: PathLike,
                  passphrase: Passphrase = None) -> str:
    """Return the version-2 sidecar text for ``data``, signed by the private key."""
    key = _load_private_key(private_key_path, passphrase)
    signature = key.sign(_CONTEXT + data)
    return json.dumps({
        "version": SIGNATURE_VERSION,
        "algorithm": _ALGORITHM,
        "key_id": _key_id(key.public_key()),
        "signature": base64.b64encode(signature).decode("ascii"),
    })


def is_envelope(sidecar_text: str) -> bool:
    """Whether a sidecar is a JSON envelope rather than a bare HMAC hex digest."""
    return sidecar_text.lstrip().startswith("{")


def _parse_envelope(sidecar_text: str) -> Optional[Dict[str, Any]]:
    """Return the envelope when it is a well-formed version-2 one, else ``None``."""
    try:
        envelope = json.loads(sidecar_text)
    except ValueError:
        return None
    if not isinstance(envelope, dict) or not isinstance(envelope.get("signature"), str):
        return None
    if envelope.get("version") != SIGNATURE_VERSION or envelope.get("algorithm") != _ALGORITHM:
        return None
    return envelope


def verification_key(public_key_path: Optional[PathLike],
                     private_key_path: Optional[PathLike]) -> Any:
    """Load the public key, deriving it from the private one on a signing machine."""
    if public_key_path is not None:
        return _load_public_key(public_key_path)
    if private_key_path is None:
        raise AutoControlException("no signing key is configured to verify with")
    return _load_private_key(private_key_path).public_key()


def envelope_failure(sidecar_text: str, data: bytes, public_key: Any) -> Optional[str]:
    """Return why ``sidecar_text`` does not sign ``data``, or ``None`` when it does."""
    envelope = _parse_envelope(sidecar_text)
    if envelope is None:
        return "malformed or unsupported signature envelope"
    expected_id = _key_id(public_key)
    signed_id = envelope.get("key_id")
    if signed_id is not None and signed_id != expected_id:
        return f"signed with a different key ({signed_id!r}, this endpoint trusts {expected_id!r})"
    try:
        signature = base64.b64decode(envelope["signature"], validate=True)
        public_key.verify(signature, _CONTEXT + data)
    except (binascii.Error, ValueError, _ed25519().invalid_signature):
        return "signature mismatch (tampered or wrong key)"
    return None
