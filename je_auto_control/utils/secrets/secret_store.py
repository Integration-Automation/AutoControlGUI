"""Encrypted secret vault used by ``${secrets.NAME}`` placeholders.

Vault format (v1) — JSON file under ``~/.je_auto_control/secrets/``:

```
{
  "version": 1,
  "salt": "<base64 16 bytes>",
  "iterations": 600000,
  "verifier": "<base64 fernet token of literal b'autocontrol-vault-v1'>",
  "items": {"NAME": "<base64 fernet token>"}
}
```

The vault key is derived from a user passphrase via PBKDF2-HMAC-SHA256
and held in memory only after :meth:`SecretManager.unlock` succeeds.
``cryptography.fernet`` provides AES-128-CBC + HMAC-SHA256 with the
standard base64 envelope. The vault is opt-in: until a passphrase is
set, every read returns ``None`` and ``${secrets.X}`` resolution raises.

The on-disk file is created with mode ``0o600`` on POSIX so other users
cannot read the encrypted blobs.
"""
import base64
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional


_VERIFIER_PLAINTEXT = b"autocontrol-vault-v1"
_KEY_ITERATIONS = 600_000
_SALT_BYTES = 16


class SecretStoreError(RuntimeError):
    """Raised when the vault file is corrupt or a passphrase is wrong."""


class SecretStoreLocked(SecretStoreError):
    """Raised when secrets are accessed but the vault is still locked."""


def default_secret_store_path() -> Path:
    """Return the per-user vault file path."""
    return Path.home() / ".je_auto_control" / "secrets" / "vault.json"


def _derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    raw = hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), salt, int(iterations), dklen=32,
    )
    return base64.urlsafe_b64encode(raw)


def _load_vault(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise SecretStoreError(f"vault unreadable: {error!r}") from error
    if not isinstance(data, dict) or data.get("version") != 1:
        raise SecretStoreError("vault format unsupported")
    return data


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows: ACL restricts by default; chmod is best-effort there.
        pass


class SecretManager:
    """In-memory cache around a Fernet-encrypted JSON vault."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else default_secret_store_path()
        self._lock = threading.RLock()
        self._fernet = None  # type: ignore[assignment]
        self._vault: Optional[dict] = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def is_initialized(self) -> bool:
        """Whether a vault file exists for this manager."""
        return self._path.exists()

    @property
    def is_unlocked(self) -> bool:
        """True after a successful :meth:`unlock`."""
        return self._fernet is not None

    def initialize(self, passphrase: str) -> None:
        """Create a fresh empty vault encrypted with ``passphrase``.

        Refuses to overwrite an existing vault — call :meth:`destroy` first
        if the user genuinely wants to start over.
        """
        if not isinstance(passphrase, str) or not passphrase:
            raise ValueError("passphrase must be a non-empty string")
        with self._lock:
            if self._path.exists():
                raise SecretStoreError("vault already exists")
            from cryptography.fernet import Fernet
            salt = os.urandom(_SALT_BYTES)
            key = _derive_key(passphrase, salt, _KEY_ITERATIONS)
            fernet = Fernet(key)
            verifier = fernet.encrypt(_VERIFIER_PLAINTEXT).decode("ascii")
            payload = {
                "version": 1,
                "salt": base64.b64encode(salt).decode("ascii"),
                "iterations": _KEY_ITERATIONS,
                "verifier": verifier,
                "items": {},
            }
            _atomic_write(self._path, payload)
            self._fernet = fernet
            self._vault = payload

    def unlock(self, passphrase: str) -> bool:
        """Derive the key, verify it, and cache it for subsequent reads."""
        with self._lock:
            data = _load_vault(self._path)
            if data is None:
                raise SecretStoreError("vault does not exist")
            from cryptography.fernet import Fernet, InvalidToken
            salt = base64.b64decode(data["salt"])
            iterations = int(data.get("iterations", _KEY_ITERATIONS))
            key = _derive_key(passphrase, salt, iterations)
            fernet = Fernet(key)
            try:
                if fernet.decrypt(data["verifier"].encode("ascii")) \
                        != _VERIFIER_PLAINTEXT:
                    return False
            except InvalidToken:
                return False
            self._fernet = fernet
            self._vault = data
            return True

    def lock(self) -> None:
        """Drop the cached key from memory."""
        with self._lock:
            self._fernet = None
            self._vault = None

    def set(self, name: str, value: str) -> None:
        """Encrypt and persist ``value`` under ``name``."""
        if not isinstance(name, str) or not name:
            raise ValueError("secret name must be a non-empty string")
        if not isinstance(value, str):
            raise ValueError("secret value must be a string")
        with self._lock:
            self._require_unlocked()
            token = self._fernet.encrypt(value.encode("utf-8")).decode("ascii")
            self._vault["items"][name] = token  # type: ignore[index]
            _atomic_write(self._path, self._vault)  # type: ignore[arg-type]

    def get(self, name: str) -> Optional[str]:
        """Return the plaintext for ``name`` or ``None`` if unset."""
        with self._lock:
            self._require_unlocked()
            token = self._vault["items"].get(name)  # type: ignore[index]
            if token is None:
                return None
            from cryptography.fernet import InvalidToken
            try:
                return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
            except InvalidToken as error:
                raise SecretStoreError(
                    f"secret {name!r} failed integrity check"
                ) from error

    def list_names(self) -> List[str]:
        """Return secret names sorted alphabetically (no values)."""
        with self._lock:
            self._require_unlocked()
            return sorted(self._vault["items"].keys())  # type: ignore[index]

    def remove(self, name: str) -> bool:
        """Delete ``name`` from the vault; return False if it was absent."""
        with self._lock:
            self._require_unlocked()
            if name not in self._vault["items"]:  # type: ignore[index]
                return False
            del self._vault["items"][name]  # type: ignore[index]
            _atomic_write(self._path, self._vault)  # type: ignore[arg-type]
            return True

    def change_passphrase(self, old: str, new: str) -> None:
        """Re-encrypt the entire vault under a new passphrase."""
        if not isinstance(new, str) or not new:
            raise ValueError("new passphrase must be a non-empty string")
        with self._lock:
            if not self.unlock(old):
                raise SecretStoreError("current passphrase incorrect")
            plaintexts: Dict[str, str] = {
                name: self.get(name) or ""
                for name in self.list_names()
            }
            self.lock()
            self._path.unlink()
            self.initialize(new)
            for name, value in plaintexts.items():
                self.set(name, value)

    def destroy(self) -> None:
        """Delete the vault file (after confirming via direct call)."""
        with self._lock:
            self.lock()
            try:
                self._path.unlink()
            except FileNotFoundError:
                pass

    def _require_unlocked(self) -> None:
        if self._fernet is None or self._vault is None:
            raise SecretStoreLocked("secret vault is locked")


default_secret_manager = SecretManager()
