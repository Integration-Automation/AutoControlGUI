"""Encrypt / decrypt action files at rest with Fernet (AES-128-CBC + HMAC).

The confidentiality companion to the HMAC signing in
:mod:`je_auto_control.utils.action_signing.signer`: keep a script's
contents secret on disk and decrypt it just before execution. The key is
derived from an arbitrary passphrase (SHA-256 → urlsafe-base64, a valid
Fernet key) or read from the per-user file at
``~/.je_auto_control/action_encryption_key`` (created on first use, 0600).
GUI-free; imports no Qt.
"""
import base64
import hashlib
import os
from pathlib import Path
from typing import Optional, Union

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_DEFAULT_KEY_PATH = Path.home() / ".je_auto_control" / "action_encryption_key"
_ENC_SUFFIX = ".enc"

KeyType = Optional[Union[bytes, str]]


def _persistent_key() -> bytes:
    """Read the per-user Fernet key, creating it (0600) on first use."""
    from cryptography.fernet import Fernet
    if _DEFAULT_KEY_PATH.exists():
        return _DEFAULT_KEY_PATH.read_bytes()
    _DEFAULT_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    generated = Fernet.generate_key()
    _DEFAULT_KEY_PATH.write_bytes(generated)
    try:
        os.chmod(_DEFAULT_KEY_PATH, 0o600)
    except OSError as error:
        autocontrol_logger.warning("encryption key chmod failed: %r", error)
    return generated


def _fernet_key(key: KeyType) -> bytes:
    """Resolve a usable Fernet key from a passphrase, or the per-user key."""
    if key is None:
        return _persistent_key()
    raw = key if isinstance(key, bytes) else str(key).encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())


def encrypt_action_file(path: Union[str, Path], key: KeyType = None) -> str:
    """Encrypt the file at ``path`` to ``<path>.enc``; return the enc path."""
    from cryptography.fernet import Fernet
    target = Path(path)
    token = Fernet(_fernet_key(key)).encrypt(target.read_bytes())
    enc_path = target.with_name(target.name + _ENC_SUFFIX)
    enc_path.write_bytes(token)
    autocontrol_logger.info("encrypted action file %s", target)
    return str(enc_path)


def decrypt_action_file(enc_path: Union[str, Path], key: KeyType = None,
                        output_path: Optional[Union[str, Path]] = None) -> str:
    """Decrypt ``enc_path`` to a plaintext file; return its path.

    ``output_path`` defaults to ``enc_path`` with the ``.enc`` suffix
    dropped. Raises :class:`AutoControlException` on a wrong key or a
    tampered file.
    """
    from cryptography.fernet import Fernet, InvalidToken
    enc = Path(enc_path)
    try:
        plaintext = Fernet(_fernet_key(key)).decrypt(enc.read_bytes())
    except InvalidToken as error:
        raise AutoControlException(
            f"cannot decrypt {enc_path!r}: wrong key or tampered file",
        ) from error
    out = _output_path(enc, output_path)
    out.write_bytes(plaintext)
    return str(out)


def _output_path(enc: Path, output_path: Optional[Union[str, Path]]) -> Path:
    if output_path is not None:
        return Path(output_path)
    if enc.name.endswith(_ENC_SUFFIX):
        return enc.with_name(enc.name[:-len(_ENC_SUFFIX)])
    return enc.with_name(enc.name + ".dec")
