"""User store + capability check for the AutoControl RBAC layer."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


class Role:
    """Enum-like string constants. Strings (not IntEnum) so JSON is readable."""
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"

    @classmethod
    def all(cls) -> List[str]:
        return [cls.VIEWER, cls.OPERATOR, cls.ADMIN]


class Capability:
    """Coarse capability tags checked by REST / MCP route guards."""
    READ_SCREEN = "read_screen"
    DRIVE_INPUT = "drive_input"
    MANAGE_HOSTS = "manage_hosts"
    MANAGE_USERS = "manage_users"
    READ_AUDIT = "read_audit"

    @classmethod
    def all(cls) -> List[str]:
        return [cls.READ_SCREEN, cls.DRIVE_INPUT, cls.MANAGE_HOSTS,
                cls.MANAGE_USERS, cls.READ_AUDIT]


_ROLE_CAPABILITIES: Dict[str, Set[str]] = {
    Role.VIEWER: {Capability.READ_SCREEN},
    Role.OPERATOR: {Capability.READ_SCREEN, Capability.DRIVE_INPUT},
    Role.ADMIN: set(Capability.all()),
}


class UserAuthError(RuntimeError):
    """Raised when a token doesn't match any known user."""


@dataclass
class UserRecord:
    """One persisted user."""
    user_id: str
    display_name: str
    role: str
    token_hash: str
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _hash_token(token: str) -> str:
    """SHA-256 hex digest — uses a fixed pepper so a leaked store alone is useless."""
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    # Pepper is intentionally fixed (not per-user salt) because the
    # store sits at ``~/.je_auto_control`` next to the rest of the
    # config — anyone with read access has every salt anyway. The
    # pepper protects against a token leaked *in isolation* (e.g. via
    # a screenshot of the user list).
    return hashlib.sha256(b"je_auto_control_pepper::" + token.encode("utf-8")).hexdigest()


def role_capabilities(role: str) -> Set[str]:
    """Return the capabilities granted by ``role`` (empty set when unknown)."""
    return set(_ROLE_CAPABILITIES.get(role, set()))


def can(role: str, capability: str) -> bool:
    """``True`` iff ``role`` grants ``capability``."""
    return capability in role_capabilities(role)


_DEFAULT_PATH_RELATIVE = ".je_auto_control/users.json"


def default_users_path() -> Path:
    return Path(os.path.expanduser("~")) / _DEFAULT_PATH_RELATIVE


class UserStore:
    """JSON-backed thread-safe user store."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else default_users_path()
        self._lock = threading.Lock()
        self._users: Dict[str, UserRecord] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def list_users(self) -> List[UserRecord]:
        with self._lock:
            return list(self._users.values())

    def add_user(self, *, user_id: str, display_name: str, role: str,
                 token: Optional[str] = None,
                 tags: Optional[List[str]] = None) -> str:
        """Add a user; returns the **plain** token (caller must persist it)."""
        if role not in Role.all():
            raise UserAuthError(f"unknown role: {role!r}")
        if not user_id:
            raise UserAuthError("user_id required")
        plain_token = token or secrets.token_urlsafe(24)
        record = UserRecord(
            user_id=user_id, display_name=display_name or user_id,
            role=role, token_hash=_hash_token(plain_token),
            tags=list(tags or []),
        )
        with self._lock:
            if user_id in self._users:
                raise UserAuthError(
                    f"user_id {user_id!r} already exists",
                )
            self._users[user_id] = record
            self._save_locked()
        return plain_token

    def remove_user(self, user_id: str) -> bool:
        with self._lock:
            removed = self._users.pop(user_id, None) is not None
            if removed:
                self._save_locked()
        return removed

    def rotate_token(self, user_id: str) -> str:
        """Generate a fresh token for an existing user; returns the plain token."""
        plain_token = secrets.token_urlsafe(24)
        with self._lock:
            existing = self._users.get(user_id)
            if existing is None:
                raise UserAuthError(f"unknown user_id: {user_id!r}")
            self._users[user_id] = UserRecord(
                user_id=existing.user_id,
                display_name=existing.display_name,
                role=existing.role,
                token_hash=_hash_token(plain_token),
                tags=list(existing.tags),
            )
            self._save_locked()
        return plain_token

    def set_role(self, user_id: str, role: str) -> None:
        if role not in Role.all():
            raise UserAuthError(f"unknown role: {role!r}")
        with self._lock:
            existing = self._users.get(user_id)
            if existing is None:
                raise UserAuthError(f"unknown user_id: {user_id!r}")
            self._users[user_id] = UserRecord(
                user_id=existing.user_id,
                display_name=existing.display_name,
                role=role,
                token_hash=existing.token_hash,
                tags=list(existing.tags),
            )
            self._save_locked()

    def authenticate(self, token: str) -> UserRecord:
        """Constant-time match a token to its user record. Raises on miss."""
        if not isinstance(token, str) or not token:
            raise UserAuthError("token required")
        expected_hash = _hash_token(token)
        with self._lock:
            for record in self._users.values():
                if hmac.compare_digest(record.token_hash, expected_hash):
                    return record
        raise UserAuthError("invalid token")

    def get(self, user_id: str) -> Optional[UserRecord]:
        with self._lock:
            return self._users.get(user_id)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            body = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        users = body.get("users") if isinstance(body, dict) else None
        if not isinstance(users, list):
            return
        with self._lock:
            for entry in users:
                if not isinstance(entry, dict):
                    continue
                record = UserRecord(
                    user_id=str(entry.get("user_id", "")),
                    display_name=str(entry.get("display_name", "")),
                    role=str(entry.get("role", Role.VIEWER)),
                    token_hash=str(entry.get("token_hash", "")),
                    tags=list(entry.get("tags") or []),
                )
                if record.user_id:
                    self._users[record.user_id] = record

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = {"users": [u.to_dict() for u in self._users.values()]}
        self._path.write_text(
            json.dumps(body, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass


_default_store: Optional[UserStore] = None
_default_lock = threading.Lock()


def default_user_store() -> UserStore:
    """Process-wide singleton (lazy)."""
    global _default_store
    with _default_lock:
        if _default_store is None:
            _default_store = UserStore()
        return _default_store


__all__ = [
    "Capability", "Role", "UserAuthError", "UserRecord", "UserStore",
    "can", "default_user_store", "role_capabilities",
]
