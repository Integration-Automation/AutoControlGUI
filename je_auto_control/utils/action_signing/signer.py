"""Sign and verify JSON action files with HMAC-SHA256.

A signed action file gets a ``<path>.sig`` sidecar holding the hex HMAC
of the file's exact bytes, keyed by a signing key. Verifying recomputes
the HMAC and compares it in constant time, so a tampered script (or one
signed with a different key) is rejected before it runs — closing the
"never trust action data from disk / the network" gap for replayed flows.

The key is either supplied explicitly or read from the per-user file at
``~/.je_auto_control/action_signing_key`` (created on first use, 0600).

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
from typing import Any, Dict, Optional, Union

from je_auto_control.utils.action_signing._key_file import load_or_create_key_file
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def _default_key_path() -> Path:
    """``~/.je_auto_control/action_signing_key``, resolved at call time."""
    return Path.home() / ".je_auto_control" / "action_signing_key"


_SIG_SUFFIX = ".sig"
_REQUIRE_ENV = "JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS"
_KEY_LENGTH = 32

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
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        return _fail(path, f"read error: {error}", raise_on_fail)
    return _verify_bytes(path, data, key, raise_on_fail)


def _verify_bytes(path: Union[str, Path], data: bytes, key: KeyType,
                  raise_on_fail: bool) -> VerifyResult:
    """Check ``data`` -- the content of ``path`` -- against its sidecar."""
    sig_path = _sig_path(Path(path))
    if not sig_path.exists():
        return _fail(path, "missing signature sidecar", raise_on_fail)
    try:
        expected = sig_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        return _fail(path, f"read error: {error}", raise_on_fail)
    actual = _digest(data, _load_or_create_key(key))
    if not hmac.compare_digest(expected.encode("utf-8"), actual.encode("utf-8")):
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
    if not signing_required():
        return
    verify_action_file(path, key, raise_on_fail=True)


def signing_required() -> bool:
    """Whether ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS`` is set (read each call)."""
    return bool(os.environ.get(_REQUIRE_ENV))


def read_signed_action_bytes(path: Union[str, Path], key: KeyType = None) -> bytes:
    """Read ``path`` once and, when enforcement is on, verify those bytes.

    The caller parses what this returns, so the content that ran is the
    content that was verified. Raises :class:`OSError` when the file cannot
    be read and :class:`AutoControlException` when it fails verification.
    """
    data = Path(path).read_bytes()
    if signing_required():
        _verify_bytes(path, data, key, raise_on_fail=True)
    return data
