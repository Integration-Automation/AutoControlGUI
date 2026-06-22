"""Idempotency-key store with stored responses (Stripe-style request dedup).

``resilience.RetryPolicy`` *re-executes* on retry, and ``work_queue`` dedups
only in-flight references — nothing caches the first result so a duplicate
request returns the *same* response without re-running the side effect. This is
the missing half of the retry story: register a key, run the work once, and
replay the stored response for any duplicate.

Pure standard library (``hashlib`` / ``json``); imports no ``PySide6``. The
clock is injectable and the store is in-memory (with JSON persistence), so TTL
expiry and replay are fully deterministic in CI.
"""
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException


class IdempotencyConflict(AutoControlException):
    """A key was reused with a different request fingerprint."""


def request_fingerprint(payload: Any) -> str:
    """Return a stable SHA-256 fingerprint of a request payload."""
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class IdempotencyStore:
    """Stores per-key request state and the first completed response."""

    def __init__(self, *, clock: Callable[[], float] = time.time,
                 ttl: Optional[float] = None) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}
        self._clock = clock
        self._ttl = ttl

    def _live(self, key: str) -> Optional[Dict[str, Any]]:
        record = self._records.get(key)
        if record is None:
            return None
        if self._ttl is not None and self._clock() - record["stored_at"] >= self._ttl:
            self._records.pop(key, None)
            return None
        return record

    def begin(self, key: str,
              request: Optional[str] = None) -> Dict[str, Any]:
        """Register ``key`` or return its existing state.

        Returns ``{status, response}`` where status is ``new`` (first time),
        ``in_progress`` (a duplicate before completion), or ``completed`` (replay
        the stored response). Raises :class:`IdempotencyConflict` when ``key`` is
        reused with a different ``request`` fingerprint.
        """
        record = self._live(key)
        if record is not None:
            if (request is not None and record["request"] is not None
                    and record["request"] != request):
                raise IdempotencyConflict(
                    f"key {key!r} reused with a different request")
            return {"status": record["status"], "response": record["response"]}
        self._records[key] = {"status": "in_progress", "request": request,
                              "response": None, "stored_at": self._clock()}
        return {"status": "new", "response": None}

    def complete(self, key: str, response: Any) -> None:
        """Record the completed ``response`` for ``key``."""
        record = self._records.get(key)
        if record is None:
            self._records[key] = {"status": "completed", "request": None,
                                  "response": response,
                                  "stored_at": self._clock()}
        else:
            record["status"] = "completed"
            record["response"] = response

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the live record for ``key`` (or ``None`` if absent/expired)."""
        record = self._live(key)
        return dict(record) if record is not None else None

    def to_dict(self) -> Dict[str, Any]:
        """Return all records as a plain dict."""
        return {key: dict(value) for key, value in self._records.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **kwargs: Any) -> "IdempotencyStore":
        """Build a store from a :meth:`to_dict` mapping."""
        store = cls(**kwargs)
        store._records = {key: dict(value) for key, value in data.items()}
        return store

    def save(self, path: str) -> str:
        """Persist the store to ``path`` as JSON; return the path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return str(out)

    @classmethod
    def load(cls, path: str, **kwargs: Any) -> "IdempotencyStore":
        """Load a store from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data, **kwargs)
