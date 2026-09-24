"""Encrypt / decrypt action files at rest with Fernet (AES-128-CBC + HMAC).

The confidentiality companion to the HMAC signing in
:mod:`je_auto_control.utils.action_signing.signer`: keep a script's
contents secret on disk and decrypt it just before execution. The key is
derived from an arbitrary passphrase with scrypt and a random salt stored in
front of the token (``ACENC1:`` + 16-byte salt + Fernet token), or read from
the per-user file at ``~/.je_auto_control/action_encryption_key`` (created
on first use, 0600). Files written before the salt existed -- a bare token
keyed by unsalted SHA-256 of the passphrase -- still decrypt.
GUI-free; imports no Qt.
"""
import base64
import hashlib
import os
from pathlib import Path
from typing import Optional, Union

from je_auto_control.utils.action_signing._key_file import load_or_create_key_file
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def _default_key_path() -> Path:
    """``~/.je_auto_control/action_encryption_key``, resolved at call time."""
    return Path.home() / ".je_auto_control" / "action_encryption_key"


_ENC_SUFFIX = ".enc"
_SALTED_MAGIC = b"ACENC1:"
_SALT_LENGTH = 16
_FERNET_KEY_LENGTH = 44  # urlsafe-base64 of 32 bytes
# scrypt cost: 2**15 * 8 * 128 bytes = 32 MiB, about 0.1 s per derivation.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 15, 8, 1

KeyType = Optional[Union[bytes, str]]


def _fernet_types() -> tuple:
    """Return ``(Fernet, InvalidToken)``, or explain why encryption is off.

    ``cryptography`` publishes no ``win_arm64`` wheel, so on Windows arm64 it
    is absent by design rather than by accident -- see ``pyproject.toml``. A
    bare ``ModuleNotFoundError`` there reads like a broken install, so name
    what is missing and what it costs.
    """
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as error:
        raise RuntimeError(
            "Action-file encryption requires cryptography (pip install cryptography). "
            "It has no Windows arm64 wheel, so encryption is unavailable there."
        ) from error
    return Fernet, InvalidToken


def _persistent_key() -> bytes:
    """Read the per-user Fernet key, creating it (0600) on first use."""
    fernet_cls, _ = _fernet_types()
    return load_or_create_key_file(
        _default_key_path(), fernet_cls.generate_key, _FERNET_KEY_LENGTH)


def _passphrase(key: Union[bytes, str]) -> bytes:
    raw = key if isinstance(key, bytes) else str(key).encode("utf-8")
    if not raw:
        raise AutoControlException("an empty passphrase encrypts nothing")
    return raw


def _scrypt_key(passphrase: bytes, salt: bytes) -> bytes:
    """Fernet key from ``passphrase`` and ``salt`` (scrypt, RFC 7914)."""
    derived = hashlib.scrypt(passphrase, salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
                             p=_SCRYPT_P, maxmem=64 * 1024 * 1024, dklen=32)
    return base64.urlsafe_b64encode(derived)


def _legacy_key(passphrase: bytes) -> bytes:
    """The unsalted key files from before ``ACENC1`` were encrypted with."""
    return base64.urlsafe_b64encode(hashlib.sha256(passphrase).digest())


def _encrypt(plaintext: bytes, key: KeyType) -> bytes:
    fernet_cls, _ = _fernet_types()
    if key is None:
        return fernet_cls(_persistent_key()).encrypt(plaintext)
    salt = os.urandom(_SALT_LENGTH)
    token = fernet_cls(_scrypt_key(_passphrase(key), salt)).encrypt(plaintext)
    return _SALTED_MAGIC + salt + token


def _decrypt(blob: bytes, key: KeyType) -> bytes:
    """Decrypt ``blob``; raise the Fernet ``InvalidToken`` on a bad key."""
    fernet_cls, _ = _fernet_types()
    if key is None:
        return fernet_cls(_persistent_key()).decrypt(blob)
    passphrase = _passphrase(key)
    if blob.startswith(_SALTED_MAGIC):
        start = len(_SALTED_MAGIC)
        salt = blob[start:start + _SALT_LENGTH]
        token = blob[start + _SALT_LENGTH:]
        return fernet_cls(_scrypt_key(passphrase, salt)).decrypt(token)
    return fernet_cls(_legacy_key(passphrase)).decrypt(blob)


def encrypt_action_file(path: Union[str, Path], key: KeyType = None) -> str:
    """Encrypt the file at ``path`` to ``<path>.enc``; return the enc path."""
    target = Path(path)
    token = _encrypt(target.read_bytes(), key)
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
    _, invalid_token = _fernet_types()
    enc = Path(enc_path)
    try:
        plaintext = _decrypt(enc.read_bytes(), key)
    except invalid_token as error:
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
