"""User store + capability check for the AutoControl RBAC layer."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


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
    #: Signing an action file with this host's key. Separate from
    #: ``DRIVE_INPUT`` so that being allowed to run actions is not being
    #: allowed to approve the files that may be run.
    SIGN_ACTIONS = "sign_actions"

    @classmethod
    def all(cls) -> List[str]:
        return [cls.READ_SCREEN, cls.DRIVE_INPUT, cls.MANAGE_HOSTS,
                cls.MANAGE_USERS, cls.READ_AUDIT, cls.SIGN_ACTIONS]


_ROLE_CAPABILITIES: Dict[str, Set[str]] = {
    Role.VIEWER: {Capability.READ_SCREEN},
    Role.OPERATOR: {Capability.READ_SCREEN, Capability.DRIVE_INPUT},
    Role.ADMIN: set(Capability.all()),
}


class UserAuthError(AutoControlException, RuntimeError):
    """Raised when a token doesn't match any known user."""


@dataclass(frozen=True)
class UserRecord:
    """One persisted user; frozen, and handed out as copies, so a caller cannot edit the store."""
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
        # Why the file on disk could not be read, if it could not. Saving
        # then would replace every user in it with what this instance holds.
        self._unreadable: Optional[str] = None
        # What the file looked like when it was last read or written, so
        # refresh() can tell that another process has changed it.
        self._loaded_stamp: Optional[Tuple[int, int]] = None
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def list_users(self) -> List[UserRecord]:
        with self._lock:
            return [_copy(record) for record in self._users.values()]

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
            tags=_tags(tags),
        )
        with self._lock:
            if user_id in self._users:
                raise UserAuthError(
                    f"user_id {user_id!r} already exists",
                )
            # authenticate() returns the first match: a second user given
            # the same token would log in as whoever was added first.
            if any(hmac.compare_digest(existing.token_hash, record.token_hash)
                   for existing in self._users.values()):
                raise UserAuthError("that token is already in use")
            self._commit_locked({**self._users, user_id: record})
        return plain_token

    def remove_user(self, user_id: str) -> bool:
        with self._lock:
            if user_id not in self._users:
                return False
            self._commit_locked({key: record for key, record in self._users.items() if key != user_id})
        return True

    def rotate_token(self, user_id: str) -> str:
        """Generate a fresh token for an existing user; returns the plain token."""
        plain_token = secrets.token_urlsafe(24)
        with self._lock:
            existing = self._users.get(user_id)
            if existing is None:
                raise UserAuthError(f"unknown user_id: {user_id!r}")
            self._commit_locked({**self._users, user_id: replace(
                existing, token_hash=_hash_token(plain_token), tags=list(existing.tags))})
        return plain_token

    def set_role(self, user_id: str, role: str) -> None:
        if role not in Role.all():
            raise UserAuthError(f"unknown role: {role!r}")
        with self._lock:
            existing = self._users.get(user_id)
            if existing is None:
                raise UserAuthError(f"unknown user_id: {user_id!r}")
            self._commit_locked({**self._users, user_id: replace(
                existing, role=role, tags=list(existing.tags))})

    def authenticate(self, token: str) -> UserRecord:
        """Constant-time match a token to its user record. Raises on miss."""
        if not isinstance(token, str) or not token:
            raise UserAuthError("token required")
        expected_hash = _hash_token(token)
        with self._lock:
            for record in self._users.values():
                if hmac.compare_digest(record.token_hash, expected_hash):
                    return _copy(record)
        raise UserAuthError("invalid token")

    def get(self, user_id: str) -> Optional[UserRecord]:
        with self._lock:
            record = self._users.get(user_id)
            return None if record is None else _copy(record)

    def refresh(self) -> bool:
        """Re-read the file if it changed on disk; ``True`` when it was re-read.

        Users are managed from another process than the server that checks
        their tokens. Without this a removed user, a rotated token or a
        lowered role kept working until that server was restarted.
        """
        stamp = self._stamp()
        with self._lock:
            if stamp == self._loaded_stamp:
                return False
        self._load()
        return True

    def _stamp(self) -> Optional[Tuple[int, int]]:
        """``(mtime_ns, size)`` of the file, or ``None`` when there is none."""
        try:
            status = self._path.stat()
        except OSError:
            return None
        return status.st_mtime_ns, status.st_size

    def _load(self) -> None:
        stamp = self._stamp()
        users, problem = self._read()
        with self._lock:
            self._users = users
            self._unreadable = problem
            self._loaded_stamp = stamp
        if problem is not None:
            autocontrol_logger.error(
                "user store %s unreadable (%s); no user can sign in and it will not be overwritten",
                self._path, problem)

    def _read(self) -> Tuple[Dict[str, UserRecord], Optional[str]]:
        """The users on disk, and why the file could not be read if it could not."""
        if not self._path.exists():
            return {}, None
        try:
            # The path is the operator's own choice of user store (constructor,
            # JE_AUTOCONTROL_RBAC_USERS or --users); no request can set it.
            body = json.loads(self._path.read_text(encoding="utf-8"))  # NOSONAR pythonsecurity:S8707  # reason: operator-configured file, never request data
        except (OSError, ValueError) as error:  # ValueError: bad JSON or not UTF-8
            return {}, repr(error)
        entries = body.get("users") if isinstance(body, dict) else None
        if not isinstance(entries, list):
            return {}, "no 'users' list"
        users: Dict[str, UserRecord] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            record = UserRecord(
                user_id=str(entry.get("user_id", "")),
                display_name=str(entry.get("display_name", "")),
                role=str(entry.get("role", Role.VIEWER)),
                token_hash=str(entry.get("token_hash", "")),
                tags=_tags(entry.get("tags")),
            )
            if record.user_id:
                users[record.user_id] = record
        return users, None

    def _commit_locked(self, users: Dict[str, UserRecord]) -> None:
        """Save ``users``, then make them the store's; on any failure nothing changes.

        The store was changed first and saved after, so a refused or failed
        save still took effect in memory: a user added to an unreadable
        store could sign in as admin, and a rotated token locked its user out.
        """
        if self._unreadable is not None:
            raise UserAuthError(
                f"user store {self._path} is unreadable ({self._unreadable}); "
                "refusing to overwrite it -- repair or remove the file first")
        body = {"users": [u.to_dict() for u in users.values()]}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # atomic_write_text: a concurrent reader saw a half-written file, and
            # its mkstemp file is 0600 from the start instead of after a chmod.
            atomic_write_text(self._path, json.dumps(body, indent=2, ensure_ascii=False))
        except OSError as error:
            raise UserAuthError(f"could not save user store {self._path}: {error}") from error
        self._users = users
        self._loaded_stamp = self._stamp()


def _copy(record: UserRecord) -> UserRecord:
    """A copy with its own tag list."""
    return replace(record, tags=list(record.tags))


def _tags(value: object) -> List[str]:
    """A tag list from caller or file input; anything but a list of strings is empty."""
    if isinstance(value, (list, tuple)):
        return [str(tag) for tag in value]
    return []


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
