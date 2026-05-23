"""Phase 6.6: TTL-tracked resume tokens for fast reconnect.

When a viewer authenticates successfully the host issues a one-shot
``resume_token`` and ships it inside the ``AUTH_OK`` JSON payload.
A viewer that drops within the TTL can reconnect using that token as
its ``token=`` parameter — the host's :class:`ResumeTokenStore` finds
it, removes it, and skips both the approval popup and any saved
view-only permission applied verbatim.

The store is in-memory only: restarting the host invalidates every
resume token, which is the safe default. Tokens are 32 URL-safe bytes
of ``secrets.token_urlsafe`` so guessing one is computationally
infeasible.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

_TOKEN_NBYTES = 32
_DEFAULT_TTL_S = 300.0  # 5 minutes — long enough for laptop sleep / Wi-Fi


@dataclass(frozen=True)
class ResumeEntry:
    """One row in the resume-token table."""
    expires_at: float
    permission: str


class ResumeTokenStore:
    """Thread-safe TTL-tracked map of resume tokens → saved permission."""

    def __init__(self, ttl: float = _DEFAULT_TTL_S) -> None:
        self._ttl = float(ttl)
        self._lock = threading.Lock()
        self._entries: Dict[str, ResumeEntry] = {}

    @property
    def ttl(self) -> float:
        return self._ttl

    def issue(self, permission: str = "full") -> str:
        """Return a fresh resume token and register it with the current TTL."""
        token = secrets.token_urlsafe(_TOKEN_NBYTES)
        with self._lock:
            self._cleanup_locked(time.monotonic())
            self._entries[token] = ResumeEntry(
                expires_at=time.monotonic() + self._ttl,
                permission=str(permission or "full"),
            )
        return token

    def list_active(self) -> Dict[str, str]:
        """Snapshot of token → permission for valid (non-expired) entries."""
        now = time.monotonic()
        with self._lock:
            self._cleanup_locked(now)
            return {k: v.permission for k, v in self._entries.items()}

    def consume(self, token: str) -> Optional[str]:
        """Remove ``token`` and return its permission, or None if absent / expired."""
        now = time.monotonic()
        with self._lock:
            self._cleanup_locked(now)
            entry = self._entries.pop(token, None)
        if entry is None or entry.expires_at < now:
            return None
        return entry.permission

    def remove(self, token: str) -> bool:
        """Best-effort removal; returns True iff the token was present."""
        with self._lock:
            return self._entries.pop(token, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            self._cleanup_locked(time.monotonic())
            return len(self._entries)

    def _cleanup_locked(self, now: float) -> None:
        expired = [k for k, v in self._entries.items() if v.expires_at < now]
        for k in expired:
            self._entries.pop(k, None)


__all__ = ["ResumeTokenStore", "ResumeEntry"]
