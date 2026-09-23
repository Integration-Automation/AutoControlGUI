"""Optimistic-concurrency version guard (local compare-and-swap store).

``http_conditional`` uses ETag for *read* caching (``If-None-Match`` / 304) but
never for *write* concurrency (``If-Match`` / version check). There was no local
compare-and-swap / versioned record store for "update only if the version is
unchanged". This fills the write side of the ETag story.

Pure standard library (``json``); imports no ``PySide6``. The version is a
monotonic int and the store is in-memory with JSON persistence, so behaviour is
fully deterministic in CI.
"""
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.json_store.json_store import atomic_write_text


class VersionConflict(AutoControlException):
    """A write/delete was attempted against a stale version."""


class VersionedStore:
    """A key/value store guarded by a monotonic version (optimistic CAS)."""

    def __init__(self) -> None:
        # put/delete are check-then-write: without a lock two writers holding
        # the same expected_version both succeeded (AC_cas_put is reachable
        # from concurrent servers).
        self._lock = threading.RLock()
        self._data: Dict[str, Dict[str, Any]] = {}
        # Highest version each key has had, kept across deletes: re-creating a
        # deleted key restarted at version 1, so a stale writer holding the
        # old v1 overwrote the new record (ABA).
        self._high_water: Dict[str, int] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Return ``{value, version}`` for ``key`` or ``None``."""
        with self._lock:
            record = self._data.get(key)
            return dict(record) if record is not None else None

    def _check(self, key: str, expected_version: Optional[int]) -> int:
        current = self._data.get(key)
        current_version = current["version"] if current else 0
        if expected_version is not None and expected_version != current_version:
            raise VersionConflict(
                f"version mismatch for {key!r}: expected {expected_version}, "
                f"have {current_version}")
        return current_version

    def put(self, key: str, value: Any, *,
            expected_version: Optional[int] = None) -> int:
        """Set ``value`` if ``expected_version`` matches; return the new version.

        ``expected_version`` of ``0`` requires the key to be absent; ``None``
        forces a blind write. Raises :class:`VersionConflict` on a mismatch.
        """
        with self._lock:
            current = self._check(key, expected_version)
            new_version = max(current, self._high_water.get(key, 0)) + 1
            self._data[key] = {"value": value, "version": new_version}
            self._high_water[key] = new_version
            return new_version

    def delete(self, key: str, *,
               expected_version: Optional[int] = None) -> bool:
        """Delete ``key`` if ``expected_version`` matches; return whether it existed."""
        with self._lock:
            if key not in self._data:
                return False
            self._check(key, expected_version)
            del self._data[key]
            return True

    def to_dict(self) -> Dict[str, Any]:
        """Return all records as a plain dict."""
        with self._lock:
            return {key: dict(value) for key, value in self._data.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any],
                  high_water: Optional[Dict[str, int]] = None) -> "VersionedStore":
        """Build a store from a :meth:`to_dict` mapping (and saved high-water marks)."""
        store = cls()
        store._data = {key: dict(value) for key, value in data.items()}
        store._high_water = {key: int(value.get("version", 0)) for key, value in data.items()}
        for key, version in (high_water or {}).items():
            store._high_water[key] = max(store._high_water.get(key, 0), int(version))
        return store

    def save(self, path: str) -> str:
        """Persist the store to ``path`` as JSON (atomically); return the path.

        The high-water marks are saved with the records: without them a key
        deleted and re-created after a reload restarted at version 1, and a
        stale writer holding the old version 1 overwrote it (ABA).
        """
        with self._lock:
            payload = {"records": self.to_dict(), "high_water": dict(self._high_water)}
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(out, json.dumps(payload, indent=2))
        return str(out)

    @classmethod
    def load(cls, path: str) -> "VersionedStore":
        """Load a store saved by :meth:`save` (or the older bare-records file)."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("records"), dict):
            return cls.from_dict(data["records"], data.get("high_water"))
        return cls.from_dict(data)


def if_match_header(version: int) -> str:
    """Return an ``If-Match`` ETag header value for a version."""
    return f'"{version}"'


def check_if_match(current_version: int, header: str) -> bool:
    """Whether an ``If-Match`` ``header`` matches ``current_version`` (``*`` = any)."""
    etag = (header or "").strip()
    if etag == "*":
        return True
    return etag.strip('"') == str(current_version)
