"""Sign and verify JSON action files: Ed25519 key pair, or HMAC-SHA256.

A signed action file gets a ``<path>.sig`` sidecar over the file's exact
bytes, so a tampered script (or one signed with a different key) is rejected
before it runs — closing the "never trust action data from disk / the
network" gap for replayed flows.

Two sidecar formats exist. **Version 2** is an Ed25519 envelope
(:mod:`.asymmetric`): the signing machine holds the private key, execution
endpoints hold the public key, and an endpoint that only verifies refuses to
sign -- which keeps the right to sign apart from the right to execute. The
keys come from explicit arguments or from the environment variables in
:mod:`.config`. The **legacy** format is the hex HMAC-SHA256 keyed by an
explicit key or the per-user file at ``~/.je_auto_control/action_signing_key``
(created on first use, 0600); it is what signing does when no key pair is
configured, and once one is configured it is accepted only in the explicit
migration mode (``JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES``).

With ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS`` set, every path that runs an
action file loads it through :func:`read_signed_action_bytes`, which reads
the file once and verifies the bytes it returns -- checking the file and
then opening it again would let it change in between.
This module is GUI-free and imports no Qt.
"""
import hashlib
import hmac
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from je_auto_control.utils.action_signing import asymmetric
from je_auto_control.utils.action_signing._key_file import load_or_create_key_file
from je_auto_control.utils.action_signing.config import (
    ACCEPT_LEGACY_ENV, PUBLIC_KEY_ENV, action_signing_config,
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlException, AutoControlSignatureException,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def _default_key_path() -> Path:
    """``~/.je_auto_control/action_signing_key``, resolved at call time."""
    return Path.home() / ".je_auto_control" / "action_signing_key"


_SIG_SUFFIX = ".sig"
_REQUIRE_ENV = "JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS"
_KEY_LENGTH = 32

KeyType = Optional[bytes | str]
KeyPath = Optional[str | Path]


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of verifying an action file against its signature sidecar."""

    path: str
    verified: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _coerce_key(key: KeyType) -> Optional[bytes]:
    if key is None:
        return None
    raw = key if isinstance(key, bytes) else str(key).encode("utf-8")
    if not raw:
        raise AutoControlException("an empty signing key signs nothing")
    return raw


def _load_or_create_key(key: KeyType) -> bytes:
    """Return the signing key: explicit if given, else the per-user file."""
    explicit = _coerce_key(key)
    if explicit is not None:
        return explicit
    return load_or_create_key_file(
        _default_key_path(), lambda: os.urandom(_KEY_LENGTH), _KEY_LENGTH)


def _sig_path(path: Path) -> Path:
    return path.with_name(path.name + _SIG_SUFFIX)


def _digest(data: bytes, key: bytes) -> str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def _signature_text(data: bytes, key: KeyType, private_key_path: KeyPath,
                    passphrase: Optional[bytes | str] = None) -> str:
    """Sign ``data`` with the key pair when one applies, else with HMAC."""
    config = action_signing_config()
    private = private_key_path
    if private is None and key is None:
        private = config.private_key_path
    if private is not None:
        return asymmetric.sign_envelope(data, private, passphrase)
    if config.verify_only:
        raise AutoControlException(
            "this endpoint verifies only (a public key and no private key are "
            "configured); sign the file on the signing machine",
        )
    return _digest(data, _load_or_create_key(key))


def sign_action_file(path: str | Path, key: KeyType = None,
                     *, private_key_path: KeyPath = None,
                     passphrase: Optional[bytes | str] = None) -> str:
    """Write a signature sidecar for the file at ``path``.

    With ``private_key_path`` -- or, when no ``key`` is given, the private key
    named by ``JE_AUTOCONTROL_ACTION_SIGNING_PRIVATE_KEY`` -- the sidecar is a
    version-2 Ed25519 envelope. Otherwise it is the HMAC-SHA256 of the file
    under ``key`` or the per-user key. An endpoint configured with a public
    key and no private key refuses instead of falling back to HMAC, raising
    :class:`AutoControlException`. ``passphrase`` unlocks a private key file
    created with one; without it ``JE_AUTOCONTROL_ACTION_SIGNING_PASSPHRASE``
    is used. Returns the sidecar path (``<path>.sig``).
    """
    target = Path(path)
    signature = _signature_text(target.read_bytes(), key, private_key_path, passphrase)
    sig_path = _sig_path(target)
    sig_path.write_text(signature, encoding="utf-8")
    autocontrol_logger.info("signed action file %s", target)
    return str(sig_path)


def verify_action_file(path: str | Path, key: KeyType = None,
                       *, raise_on_fail: bool = False,
                       public_key_path: KeyPath = None) -> VerifyResult:
    """Verify the action file at ``path`` against its ``.sig`` sidecar.

    A version-2 sidecar is checked with ``public_key_path`` or the configured
    public key; no private key is read. An HMAC sidecar is checked with
    ``key`` or the per-user key, and refused when a key pair is configured
    unless migration mode is on. Returns a :class:`VerifyResult`. With
    ``raise_on_fail`` set, an unverified file raises
    :class:`AutoControlSignatureException` (an ``AutoControlException``) instead.
    """
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        return _fail(path, f"read error: {error}", raise_on_fail)
    return _verify_bytes(path, data, key, raise_on_fail, public_key_path)


def _signature_failure(sidecar: str, data: bytes, key: KeyType,
                       public_key_path: KeyPath) -> Optional[str]:
    """Return why ``sidecar`` does not sign ``data``, or ``None`` when it does."""
    config = action_signing_config()
    public = public_key_path if public_key_path is not None else config.public_key_path
    key_pair = public is not None or config.private_key_path is not None
    if asymmetric.is_envelope(sidecar):
        if not key_pair:
            return f"Ed25519 signature but no public key is configured (set {PUBLIC_KEY_ENV})"
        trusted = asymmetric.verification_key(public, config.private_key_path)
        return asymmetric.envelope_failure(sidecar, data, trusted)
    if key_pair and not config.accept_legacy:
        return ("legacy HMAC signature refused: sign the file again with the key pair, "
                f"or set {ACCEPT_LEGACY_ENV}=1 while migrating")
    if key_pair:
        autocontrol_logger.warning(
            "accepting a legacy HMAC action signature because %s is set", ACCEPT_LEGACY_ENV)
    actual = _digest(data, _load_or_create_key(key))
    if not hmac.compare_digest(sidecar.encode("utf-8"), actual.encode("utf-8")):
        return "signature mismatch (tampered or wrong key)"
    return None


def _verify_bytes(path: str | Path, data: bytes, key: KeyType,
                  raise_on_fail: bool, public_key_path: KeyPath = None) -> VerifyResult:
    """Check ``data`` -- the content of ``path`` -- against its sidecar."""
    sig_path = _sig_path(Path(path))
    if not sig_path.exists():
        return _fail(path, "missing signature sidecar", raise_on_fail)
    try:
        expected = sig_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        return _fail(path, f"read error: {error}", raise_on_fail)
    reason = _signature_failure(expected, data, key, public_key_path)
    if reason is not None:
        return _fail(path, reason, raise_on_fail)
    return VerifyResult(str(path), True, "signature valid")


def _fail(path: str | Path, reason: str,
          raise_on_fail: bool) -> VerifyResult:
    if raise_on_fail:
        raise AutoControlSignatureException(
            f"action file {path!r} failed verification: {reason}",
        )
    autocontrol_logger.info("action file %r unverified: %s", path, reason)
    return VerifyResult(str(path), False, reason)


def require_signed_actions(path: str | Path,
                           key: KeyType = None) -> None:
    """Verify ``path`` only when signed-action enforcement is enabled.

    Enforcement is opt-in via the ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS``
    environment variable; when unset this is a no-op so existing flows are
    unaffected. Raises :class:`AutoControlException` on an unverified file.
    """
    if not signing_required():
        return
    verify_action_file(path, key, raise_on_fail=True)


def signing_required() -> bool:
    """Whether ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS`` is set (read each call)."""
    return bool(os.environ.get(_REQUIRE_ENV))


def read_signed_action_bytes(path: str | Path, key: KeyType = None) -> bytes:
    """Read ``path`` once and, when enforcement is on, verify those bytes.

    The caller parses what this returns, so the content that ran is the
    content that was verified. Raises :class:`OSError` when the file cannot
    be read and :class:`AutoControlException` when it fails verification.
    """
    data = Path(path).read_bytes()
    if signing_required():
        _verify_bytes(path, data, key, raise_on_fail=True)
    return data
