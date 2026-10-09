"""Content-addressed blob storage behind the sync server's ``/blobs`` routes.

Config sync moves small entries through the bucket; a file too large for an
entry (a long script, a template image) travels as an *asset*, named by its
SHA-256. :class:`BlobStore` is where the signaling server keeps those: one
folder per account, one file per digest, so the same content is stored once
and a blob cannot be fetched under another account's name.

Three limits bound what a client can make the server hold: the size of one
blob, the total an account may store, and how many accounts may store
anything. Content is hashed before it is kept -- a blob can only ever be
stored under the digest of its own bytes -- and is written to a temporary
file and renamed, so a reader never sees half of one.

The quota check and the write are one step for every process that shares the
folder: a write holds the lock file ``<root>/store.lock`` (the helper the
shared JSON stores use), so two server processes cannot each admit a blob the
other has not counted. Nothing here deletes a blob by itself; the listing
reports each blob's age so a client can collect the ones no entry refers to
(:func:`~je_auto_control.utils.config_sync.assets.collect_unreferenced_blobs`).

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from je_auto_control.utils.config_sync.bucket import ConfigSyncError

#: The largest single blob a store accepts by default.
DEFAULT_MAX_BLOB_BYTES = 16 * 1024 * 1024
#: How much one account may store in total by default.
DEFAULT_BLOB_QUOTA_BYTES = 256 * 1024 * 1024
#: How many accounts may hold blobs in one store by default.
DEFAULT_MAX_BLOB_USERS = 1024
_SHA256_HEX_CHARS = 64
_HEX = frozenset("0123456789abcdef")
_TEMP_PREFIX = ".incoming-"


class BlobStoreError(ConfigSyncError):
    """A blob could not be stored, read or removed."""


class BlobDigestError(BlobStoreError):
    """The name is not a SHA-256 digest, or the content does not hash to it."""


class BlobTooLargeError(BlobStoreError):
    """One blob is larger than the store accepts."""


class BlobQuotaError(BlobStoreError):
    """Storing the blob would take the account over its total quota."""


class BlobCapacityError(BlobStoreError):
    """A new account's first blob would exceed the store's account limit."""


class BlobStoreBusyError(BlobStoreError):
    """Another process held the store's lock file for too long; nothing was written."""


def default_blob_dir() -> Path:
    """``~/.je_auto_control/config_sync_blobs``, resolved at call time."""
    return Path.home() / ".je_auto_control" / "config_sync_blobs"


def checked_blob_digest(value: Any) -> str:
    """``value`` as a lower-case SHA-256 hex digest, or :class:`BlobDigestError`."""
    text = value.lower() if isinstance(value, str) else ""
    if len(text) != _SHA256_HEX_CHARS or not set(text) <= _HEX:
        raise BlobDigestError("a blob is named by the 64 hex characters of its SHA-256")
    return text


class BlobStore:
    """Per-account, content-addressed files under one directory.

    ``root`` of ``None`` means :func:`default_blob_dir`. Nothing is created
    on disk until the first blob is stored, so building a store (as
    ``create_app`` does) has no side effect.
    """

    def __init__(self, root: str | Path | None = None, *,
                 max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES,
                 quota_bytes: int = DEFAULT_BLOB_QUOTA_BYTES,
                 max_users: int = DEFAULT_MAX_BLOB_USERS) -> None:
        self._configured_root = root
        self._max_blob_bytes = max(1, int(max_blob_bytes))
        self._quota_bytes = max(1, int(quota_bytes))
        self._max_users = max(1, int(max_users))
        # One writer at a time: the quota check and the write are one step.
        # This lock is for the threads of one process; the lock file taken in
        # put() is for the other processes sharing the folder.
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        """Where the blobs live (resolving the default if none was given)."""
        configured = self._configured_root
        return Path(configured) if configured is not None else default_blob_dir()

    @property
    def max_blob_bytes(self) -> int:
        """The largest single blob this store accepts."""
        return self._max_blob_bytes

    @property
    def quota_bytes(self) -> int:
        """How much one account may store in total."""
        return self._quota_bytes

    def _account_dir(self, user_id: str) -> Path:
        # The account is a folder named by a hash of its id: whatever the id
        # contains, it cannot name a path, and two ids cannot share a folder.
        if not isinstance(user_id, str) or not user_id:
            raise BlobStoreError("a blob belongs to an account: user_id is required")
        return self.root / hashlib.sha256(user_id.encode("utf-8")).hexdigest()

    def _blob(self, user_id: str, sha256: Any) -> Path:
        return self._account_dir(user_id) / checked_blob_digest(sha256)

    @staticmethod
    def _entries(folder: Path) -> List[os.DirEntry[str]]:
        """The finished blobs in an account folder (none when it does not exist)."""
        try:
            with os.scandir(folder) as found:
                return [entry for entry in found
                        if entry.is_file() and not entry.name.startswith(_TEMP_PREFIX)]
        except FileNotFoundError:
            return []

    def has(self, user_id: str, sha256: Any) -> bool:
        """Whether the account holds content for ``sha256``."""
        return self._blob(user_id, sha256).is_file()

    def get(self, user_id: str, sha256: Any) -> Optional[bytes]:
        """The content the account stored under ``sha256``; ``None`` if absent."""
        path = self._blob(user_id, sha256)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as error:
            raise BlobStoreError(f"cannot read blob {path.name}: {error}") from error

    def usage(self, user_id: str) -> Dict[str, Any]:
        """``{"used", "quota", "count", "max_blob_bytes", "blobs"}`` for the account.

        Each of ``blobs`` is ``{"sha256", "size", "age_s"}``; ``age_s`` is how
        long ago, by this machine's clock, the blob was last stored (storing
        content the account already holds counts), so a reader on another
        machine needs no clock of its own to tell an old blob from a new one.
        """
        try:
            stats = {entry.name: entry.stat()
                     for entry in self._entries(self._account_dir(user_id))}
        except OSError as error:
            raise BlobStoreError(f"cannot list blobs: {error}") from error
        now = time.time()
        blobs = [{"sha256": digest, "size": stat.st_size,
                  "age_s": max(0.0, now - stat.st_mtime)}
                 for digest, stat in sorted(stats.items())]
        return {"used": sum(stat.st_size for stat in stats.values()),
                "quota": self._quota_bytes, "count": len(blobs),
                "max_blob_bytes": self._max_blob_bytes, "blobs": blobs}

    def put(self, user_id: str, sha256: Any, data: bytes) -> bool:
        """Keep ``data`` under ``sha256``; whether it was new to the account.

        Raises :class:`BlobDigestError` when ``data`` does not hash to
        ``sha256``, :class:`BlobTooLargeError` over the per-blob limit,
        :class:`BlobQuotaError` when the account's total would pass its
        quota and :class:`BlobCapacityError` when a new account would pass
        the account limit. Storing content the account already holds
        succeeds and writes nothing -- it only marks the blob as stored now,
        so housekeeping that goes by age leaves it alone.
        :class:`BlobStoreBusyError` when another process kept the store's
        lock file for too long.
        """
        digest = checked_blob_digest(sha256)
        if len(data) > self._max_blob_bytes:
            raise BlobTooLargeError(
                f"blob is {len(data)} bytes; the limit is {self._max_blob_bytes}")
        if hashlib.sha256(data).hexdigest() != digest:
            raise BlobDigestError("content does not match the SHA-256 it was sent under")
        from je_auto_control.utils.json_store.json_store import _file_lock
        folder = self._account_dir(user_id)
        with self._lock:
            try:
                with _file_lock(self.root / "store"):
                    return self._write(folder, digest, data)
            except TimeoutError as error:
                raise BlobStoreBusyError(
                    f"blob store {self.root} is locked by another process") from error
            except OSError as error:
                raise BlobStoreError(f"cannot store blob {digest}: {error}") from error

    def _write(self, folder: Path, digest: str, data: bytes) -> bool:
        target = folder / digest
        if target.is_file():
            os.utime(target)            # held already; it is as good as stored now
            return False
        used = sum(entry.stat().st_size for entry in self._entries(folder))
        if used + len(data) > self._quota_bytes:
            raise BlobQuotaError(
                f"the account's quota is {self._quota_bytes} bytes and {used} are used; "
                f"{len(data)} more does not fit")
        if not folder.is_dir():
            self._require_room_for_account()
            folder.mkdir(parents=True, exist_ok=True)
        part = folder / f"{_TEMP_PREFIX}{secrets.token_hex(8)}"
        try:
            part.write_bytes(data)
            os.replace(part, target)
        finally:
            part.unlink(missing_ok=True)
        return True

    def _require_room_for_account(self) -> None:
        try:
            with os.scandir(self.root) as found:
                accounts = sum(1 for entry in found if entry.is_dir())
        except FileNotFoundError:
            accounts = 0
        if accounts >= self._max_users:
            raise BlobCapacityError(f"store already holds blobs for {accounts} accounts")

    def delete(self, user_id: str, sha256: Any) -> bool:
        """Remove the account's blob; ``False`` when it held none."""
        path = self._blob(user_id, sha256)
        with self._lock:
            try:
                path.unlink()
            except FileNotFoundError:
                return False
            except OSError as error:
                raise BlobStoreError(f"cannot delete blob {path.name}: {error}") from error
        return True


__all__ = [
    "BlobCapacityError", "BlobDigestError", "BlobQuotaError", "BlobStore", "BlobStoreBusyError",
    "BlobStoreError", "BlobTooLargeError", "DEFAULT_BLOB_QUOTA_BYTES", "DEFAULT_MAX_BLOB_BYTES",
    "DEFAULT_MAX_BLOB_USERS", "checked_blob_digest", "default_blob_dir",
]
