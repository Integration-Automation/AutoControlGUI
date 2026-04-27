"""Stable viewer-side identity used for the trust-list flow.

Each viewer machine generates a 32-hex-character random ID on first run
and persists it under ``~/.je_auto_control/viewer_id``. The ID is sent
inside the WebRTC auth message so a host that has previously trusted this
viewer can auto-accept future connections without prompting the user.

Security note: a viewer_id is not a cryptographic credential — it is a
stable identifier that combines with the shared HMAC token to gate
access. If a trusted viewer_id leaks, the host should clear it from the
trust list. For higher assurance use a TLS client certificate or rotate
tokens.
"""
import os
import re
import secrets
from pathlib import Path
from typing import Optional


_VIEWER_ID_HEX_LEN = 32
_DEFAULT_PATH_RELATIVE = ".je_auto_control/viewer_id"
_VIEWER_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class ViewerIdError(ValueError):
    """Raised when a viewer ID is malformed."""


def generate_viewer_id() -> str:
    """Return a fresh random 32-hex-character viewer ID."""
    return secrets.token_hex(_VIEWER_ID_HEX_LEN // 2)


def validate_viewer_id(value: str) -> str:
    """Return ``value`` unchanged if it is a valid viewer ID."""
    if not isinstance(value, str) or _VIEWER_ID_PATTERN.fullmatch(value) is None:
        raise ViewerIdError(
            f"viewer_id must be {_VIEWER_ID_HEX_LEN} hex chars, got {value!r}",
        )
    return value


def default_viewer_id_path() -> Path:
    home = Path(os.path.expanduser("~"))
    return home / _DEFAULT_PATH_RELATIVE


def load_or_create_viewer_id(path: Optional[Path] = None) -> str:
    """Return the persisted viewer ID, creating one on first call."""
    target = Path(path) if path is not None else default_viewer_id_path()
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8").strip()
            return validate_viewer_id(existing)
        except (OSError, ViewerIdError):
            pass
    new_id = generate_viewer_id()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_id, encoding="utf-8")
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    except OSError:
        pass
    return new_id


__all__ = [
    "ViewerIdError",
    "generate_viewer_id",
    "validate_viewer_id",
    "default_viewer_id_path",
    "load_or_create_viewer_id",
]
