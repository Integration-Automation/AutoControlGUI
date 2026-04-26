"""Stable, persistent host identifier exposed during the auth handshake.

Each host has a 9-digit numeric ID — short enough to read aloud, long
enough to be hard to guess by chance. The ID is generated on first use
and cached at ``~/.je_auto_control/remote_host_id`` so it stays the same
across restarts; users hand the ID + token + address to the people they
want to connect, and viewers can verify ``expected_host_id`` after auth
to defend against TCP-level impersonation.

The ID is *not* a substitute for the auth token — it is broadcast in
plain text inside ``AUTH_OK`` and is meant to be shared. Token-based
HMAC auth gates the actual session.
"""
import os
import re
import secrets
from pathlib import Path
from typing import Optional

_HOST_ID_DIGITS = 9
_DEFAULT_PATH_RELATIVE = ".je_auto_control/remote_host_id"
_HOST_ID_PATTERN = re.compile(r"^\d{9}$")


class HostIdError(ValueError):
    """Raised when a host ID is malformed."""


def generate_host_id() -> str:
    """Return a fresh random 9-digit host ID (zero-padded)."""
    return f"{secrets.randbelow(10 ** _HOST_ID_DIGITS):0{_HOST_ID_DIGITS}d}"


def validate_host_id(value: str) -> str:
    """Return ``value`` unchanged if it is a valid 9-digit host ID."""
    if not isinstance(value, str) or _HOST_ID_PATTERN.fullmatch(value) is None:
        raise HostIdError(
            f"host_id must be {_HOST_ID_DIGITS} numeric digits, got {value!r}"
        )
    return value


def format_host_id(value: str) -> str:
    """Render a host ID with grouping for display (e.g. ``123 456 789``)."""
    digits = validate_host_id(value)
    return f"{digits[:3]} {digits[3:6]} {digits[6:]}"


def parse_host_id(value: str) -> str:
    """Strip whitespace / separators from user input and validate."""
    if not isinstance(value, str):
        raise HostIdError(f"host_id must be a string, got {type(value).__name__}")
    cleaned = re.sub(r"[\s\-_]", "", value)
    return validate_host_id(cleaned)


def default_host_id_path() -> Path:
    """Return the on-disk path used to persist the host ID."""
    home = Path(os.path.expanduser("~"))
    return home / _DEFAULT_PATH_RELATIVE


def load_or_create_host_id(path: Optional[Path] = None) -> str:
    """Return the persisted host ID, creating one on first call."""
    target = Path(path) if path is not None else default_host_id_path()
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8").strip()
            return validate_host_id(existing)
        except (OSError, HostIdError):
            # Corrupt / unreadable — regenerate rather than fail the host.
            pass
    new_id = generate_host_id()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_id, encoding="utf-8")
    except OSError:
        # Persisting is best-effort; an in-memory ID still works for the
        # current process even if the home directory is read-only.
        pass
    return new_id
