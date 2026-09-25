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
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.json_store.json_store import _file_lock, atomic_write_text


_VERIFIER_PLAINTEXT = b"autocontrol-vault-v1"
_KEY_ITERATIONS = 600_000
_SALT_BYTES = 16


def _fernet_types() -> tuple:
    """Return ``(Fernet, InvalidToken)``, or explain why the vault cannot open.

    ``cryptography`` publishes no ``win_arm64`` wheel, so on Windows arm64 it
    is absent by design rather than by accident -- see ``pyproject.toml``. A
    bare ``ModuleNotFoundError`` there reads like a broken install, so name
    what is missing and what it costs.
    """
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as error:
        raise RuntimeError(
            "The secret vault requires cryptography (pip install cryptography). "
            "It has no Windows arm64 wheel, so the vault is unavailable there."
        ) from error
    return Fernet, InvalidToken


class SecretStoreError(AutoControlException, RuntimeError):
    """Raised when the vault file is corrupt or a passphrase is wrong.

    Part of the ``AutoControlException`` family like every framework error, so
    the containment boundaries catch it; still a ``RuntimeError`` for callers
    that caught it as one.
    """


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
    _check_vault_fields(data)
    return data


def _check_vault_fields(data: dict) -> None:
    """Raise ``SecretStoreError`` for a vault whose fields cannot be used.

    A missing salt raised ``KeyError`` from :meth:`SecretManager.unlock`, and
    ``iterations: 0`` a ``ValueError``, both outside the family.
    """
    iterations = data.get("iterations", _KEY_ITERATIONS)
    fields_ok = (
        isinstance(data.get("salt"), str)
        and isinstance(data.get("verifier"), str)
        and isinstance(data.get("items", {}), dict)
        and isinstance(iterations, int) and not isinstance(iterations, bool)
        and iterations > 0
    )
    if not fields_ok:
        raise SecretStoreError("vault fields are missing or invalid")
    try:
        base64.b64decode(data["salt"], validate=True)
    except ValueError as error:  # binascii.Error is a ValueError
        raise SecretStoreError("vault salt is not base64") from error


def _atomic_write(path: Path, payload: dict) -> None:
    """Replace the vault file; the temp file is unique and 0600 from creation.

    A fixed ``vault.json.tmp`` let two writers truncate each other's temp file
    and fail the rename on Windows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True))
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows: ACL restricts by default; chmod is best-effort there.
        pass


def _new_vault(passphrase: str) -> Tuple[Any, dict]:
    """Return ``(fernet, payload)`` for an empty vault keyed by ``passphrase``."""
    fernet_cls, _ = _fernet_types()
    salt = os.urandom(_SALT_BYTES)
    fernet = fernet_cls(_derive_key(passphrase, salt, _KEY_ITERATIONS))
    payload = {
        "version": 1,
        "salt": base64.b64encode(salt).decode("ascii"),
        "iterations": _KEY_ITERATIONS,
        "verifier": fernet.encrypt(_VERIFIER_PLAINTEXT).decode("ascii"),
        "items": {},
    }
    return fernet, payload


class SecretManager:
    """In-memory cache around a Fernet-encrypted JSON vault."""

    def __init__(self, path: Optional[Path] = None) -> None:
        # Only an explicit path is kept; the default is resolved on every
        # use, because this module builds a shared instance while the
        # package imports -- before a test suite's conftest.py can set HOME.
        self._explicit_path: Optional[Path] = (
            Path(path) if path is not None else None)
        self._lock = threading.RLock()
        self._fernet = None  # type: ignore[assignment]
        self._vault: Optional[dict] = None

    @property
    def _path(self) -> Path:
        return self._explicit_path or default_secret_store_path()

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
        with self._lock, self._vault_locked():
            if self._path.exists():
                raise SecretStoreError("vault already exists")
            fernet, payload = _new_vault(passphrase)
            _atomic_write(self._path, payload)
            self._fernet = fernet
            self._vault = payload

    def unlock(self, passphrase: str) -> bool:
        """Derive the key, verify it, and cache it for subsequent reads."""
        with self._lock:
            data = _load_vault(self._path)
            if data is None:
                raise SecretStoreError("vault does not exist")
            fernet_cls, invalid_token = _fernet_types()
            salt = base64.b64decode(data["salt"])
            iterations = int(data.get("iterations", _KEY_ITERATIONS))
            key = _derive_key(passphrase, salt, iterations)
            fernet = fernet_cls(key)
            try:
                if fernet.decrypt(data["verifier"].encode("ascii")) \
                        != _VERIFIER_PLAINTEXT:
                    return False
            except invalid_token:
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
        with self._lock, self._vault_locked():
            fernet, vault = self._require_unlocked()
            token = fernet.encrypt(value.encode("utf-8")).decode("ascii")
            vault["items"][name] = token
            _atomic_write(self._path, vault)

    def get(self, name: str) -> Optional[str]:
        """Return the plaintext for ``name`` or ``None`` if unset."""
        with self._lock:
            fernet, vault = self._require_unlocked()
            token = vault["items"].get(name)
            if token is None:
                return None
            _, invalid_token = _fernet_types()
            try:
                return fernet.decrypt(token.encode("ascii")).decode("utf-8")
            except invalid_token as error:
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
        with self._lock, self._vault_locked():
            self._require_unlocked()
            if name not in self._vault["items"]:  # type: ignore[index]
                return False
            del self._vault["items"][name]  # type: ignore[index]
            _atomic_write(self._path, self._vault)  # type: ignore[arg-type]
            return True

    def change_passphrase(self, old: str, new: str) -> None:
        """Re-encrypt the entire vault under a new passphrase.

        The new vault is built in memory and replaces the old file in one
        atomic write: it used to delete the vault and re-add each secret with
        its own write, so an error or crash part-way lost every secret not
        yet re-added.
        """
        if not isinstance(new, str) or not new:
            raise ValueError("new passphrase must be a non-empty string")
        with self._lock, self._vault_locked():
            if not self.unlock(old):
                raise SecretStoreError("current passphrase incorrect")
            plaintexts: Dict[str, str] = {
                name: self.get(name) or ""
                for name in self.list_names()
            }
            fernet, payload = _new_vault(new)
            payload["items"] = {
                name: fernet.encrypt(value.encode("utf-8")).decode("ascii")
                for name, value in plaintexts.items()
            }
            _atomic_write(self._path, payload)
            self._fernet = fernet
            self._vault = payload

    def destroy(self) -> None:
        """Delete the vault file (after confirming via direct call)."""
        with self._lock:
            self.lock()
            try:
                self._path.unlink()
            except FileNotFoundError:
                pass

    @contextmanager
    def _vault_locked(self) -> Iterator[None]:
        """Hold the vault's lock file across a read-modify-write.

        Re-reading before each write was not enough: two managers (the GUI
        and a service) could both read, both change and both write, and the
        second write dropped the first one's secret.
        """
        try:
            lock = _file_lock(self._path)
            lock.__enter__()
        except TimeoutError as error:
            raise SecretStoreError("the vault is locked by another process") from error
        try:
            yield
        finally:
            lock.__exit__(None, None, None)

    def _require_unlocked(self) -> Tuple[Any, dict]:
        """Return the key and the vault as it is on disk now, or raise if locked.

        Every operation re-reads the file: each manager used to write back its
        own cached copy, so two of them on one vault (the GUI and a service
        process) silently undid each other's changes. A vault re-keyed
        elsewhere locks this manager again.
        """
        fernet, vault = self._fernet, self._vault
        if fernet is None or vault is None:
            raise SecretStoreLocked("secret vault is locked")
        fresh = _load_vault(self._path)
        if fresh is None:
            self.lock()
            raise SecretStoreLocked("secret vault no longer exists")
        if (fresh.get("salt"), fresh.get("verifier")) != (vault.get("salt"), vault.get("verifier")):
            self.lock()
            raise SecretStoreLocked("secret vault was re-keyed; unlock it again")
        fresh.setdefault("items", {})
        self._vault = fresh
        return fernet, fresh


default_secret_manager = SecretManager()
