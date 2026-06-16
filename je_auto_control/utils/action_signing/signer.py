"""Sign and verify JSON action files with HMAC-SHA256.

A signed action file gets a ``<path>.sig`` sidecar holding the hex HMAC
of the file's exact bytes, keyed by a signing key. Verifying recomputes
the HMAC and compares it in constant time, so a tampered script (or one
signed with a different key) is rejected before it runs — closing the
"never trust action data from disk / the network" gap for replayed flows.

The key is either supplied explicitly or read from the per-user file at
``~/.je_auto_control/action_signing_key`` (created on first use, 0600).
This module is GUI-free and imports no Qt.
"""
import hashlib
import hmac
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_DEFAULT_KEY_PATH = Path.home() / ".je_auto_control" / "action_signing_key"
_SIG_SUFFIX = ".sig"
_REQUIRE_ENV = "JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS"

KeyType = Optional[Union[bytes, str]]


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
    return key if isinstance(key, bytes) else str(key).encode("utf-8")


def _load_or_create_key(key: KeyType) -> bytes:
    """Return the signing key: explicit if given, else the per-user file."""
    explicit = _coerce_key(key)
    if explicit is not None:
        return explicit
    if _DEFAULT_KEY_PATH.exists():
        return _DEFAULT_KEY_PATH.read_bytes()
    _DEFAULT_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    generated = os.urandom(32)
    _DEFAULT_KEY_PATH.write_bytes(generated)
    try:
        os.chmod(_DEFAULT_KEY_PATH, 0o600)
    except OSError as error:
        autocontrol_logger.warning("signing key chmod failed: %r", error)
    return generated


def _sig_path(path: Path) -> Path:
    return path.with_name(path.name + _SIG_SUFFIX)


def _digest(data: bytes, key: bytes) -> str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def sign_action_file(path: Union[str, Path], key: KeyType = None) -> str:
    """Write an HMAC-SHA256 signature sidecar for the file at ``path``.

    Returns the sidecar path (``<path>.sig``).
    """
    target = Path(path)
    signature = _digest(target.read_bytes(), _load_or_create_key(key))
    sig_path = _sig_path(target)
    sig_path.write_text(signature, encoding="utf-8")
    autocontrol_logger.info("signed action file %s", target)
    return str(sig_path)


def verify_action_file(path: Union[str, Path], key: KeyType = None,
                       *, raise_on_fail: bool = False) -> VerifyResult:
    """Verify the action file at ``path`` against its ``.sig`` sidecar.

    Returns a :class:`VerifyResult`. With ``raise_on_fail`` set, an
    unverified file raises :class:`AutoControlException` instead.
    """
    target = Path(path)
    sig_path = _sig_path(target)
    if not sig_path.exists():
        return _fail(path, "missing signature sidecar", raise_on_fail)
    try:
        expected = sig_path.read_text(encoding="utf-8").strip()
        actual = _digest(target.read_bytes(), _load_or_create_key(key))
    except OSError as error:
        return _fail(path, f"read error: {error}", raise_on_fail)
    if not hmac.compare_digest(expected, actual):
        return _fail(path, "signature mismatch (tampered or wrong key)",
                     raise_on_fail)
    return VerifyResult(str(path), True, "signature valid")


def _fail(path: Union[str, Path], reason: str,
          raise_on_fail: bool) -> VerifyResult:
    if raise_on_fail:
        raise AutoControlException(
            f"action file {path!r} failed verification: {reason}",
        )
    autocontrol_logger.info("action file %r unverified: %s", path, reason)
    return VerifyResult(str(path), False, reason)


def require_signed_actions(path: Union[str, Path],
                           key: KeyType = None) -> None:
    """Verify ``path`` only when signed-action enforcement is enabled.

    Enforcement is opt-in via the ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS``
    environment variable; when unset this is a no-op so existing flows are
    unaffected. Raises :class:`AutoControlException` on an unverified file.
    """
    if not os.environ.get(_REQUIRE_ENV):
        return
    verify_action_file(path, key, raise_on_fail=True)
