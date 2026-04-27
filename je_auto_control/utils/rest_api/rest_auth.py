"""Bearer-token auth + per-client rate-limit gate for the REST server.

Kept separate from ``rest_server`` so the auth policy can be unit-tested
without spinning up an HTTP server, and so future schemes (mTLS, HMAC,
OAuth) can plug in without touching dispatch code.

Token model:
  * Tokens are URL-safe random strings, ``_DEFAULT_TOKEN_BYTES`` of entropy.
  * Comparison uses :func:`secrets.compare_digest` to avoid timing leaks.
  * The token is generated once at server start and surfaced on the
    ``RestApiServer`` instance so the GUI / CLI can show it to the user.

Rate limit:
  * One token bucket per client IP, refilled at ``_REQUESTS_PER_MINUTE``
    with a burst of ``_BURST``. Failures over a short window are counted
    separately and trigger a 429 rather than a 401, so a brute-force scan
    is forced to slow down even when the token is wrong.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional


_DEFAULT_TOKEN_BYTES = 24
_REQUESTS_PER_MINUTE = 120.0
_BURST = 30.0
_FAILED_AUTH_WINDOW_S = 60.0
_FAILED_AUTH_THRESHOLD = 8


def generate_token() -> str:
    """Return a fresh URL-safe random bearer token."""
    return secrets.token_urlsafe(_DEFAULT_TOKEN_BYTES)


def constant_time_equal(provided: str, expected: str) -> bool:
    """Timing-safe string compare; both args must be ``str``."""
    return secrets.compare_digest(provided, expected)


@dataclass
class _Bucket:
    tokens: float
    last_refill: float
    failed: int = 0
    failed_window_start: float = 0.0


class RestAuthGate:
    """Bearer-token check + per-IP token bucket.

    ``check(...)`` is the only entry point handlers should call.
    Returns one of ``"ok"``, ``"unauthorized"``, ``"rate_limited"``,
    ``"locked_out"``.
    """

    def __init__(self, expected_token: str,
                 *, requests_per_minute: float = _REQUESTS_PER_MINUTE,
                 burst: float = _BURST) -> None:
        self._token = expected_token
        self._rate_per_s = float(requests_per_minute) / 60.0
        self._burst = float(burst)
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    @property
    def expected_token(self) -> str:
        return self._token

    def check(self, *, client_ip: str, header_value: Optional[str]) -> str:
        if not self._consume_token(client_ip):
            return "rate_limited"
        if self._is_locked_out(client_ip):
            return "locked_out"
        if not _matches_bearer(header_value, self._token):
            self._note_failure(client_ip)
            return "unauthorized"
        self._reset_failures(client_ip)
        return "ok"

    def _consume_token(self, client_ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(client_ip)
            if bucket is None:
                bucket = _Bucket(tokens=self._burst, last_refill=now)
                self._buckets[client_ip] = bucket
            elapsed = now - bucket.last_refill
            bucket.last_refill = now
            bucket.tokens = min(
                self._burst, bucket.tokens + elapsed * self._rate_per_s,
            )
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True
            return False

    def _is_locked_out(self, client_ip: str) -> bool:
        with self._lock:
            bucket = self._buckets.get(client_ip)
            if bucket is None:
                return False
            now = time.monotonic()
            if now - bucket.failed_window_start > _FAILED_AUTH_WINDOW_S:
                bucket.failed = 0
                bucket.failed_window_start = now
            return bucket.failed >= _FAILED_AUTH_THRESHOLD

    def _note_failure(self, client_ip: str) -> None:
        with self._lock:
            bucket = self._buckets.setdefault(
                client_ip,
                _Bucket(tokens=self._burst, last_refill=time.monotonic()),
            )
            now = time.monotonic()
            if now - bucket.failed_window_start > _FAILED_AUTH_WINDOW_S:
                bucket.failed = 0
                bucket.failed_window_start = now
            bucket.failed += 1

    def _reset_failures(self, client_ip: str) -> None:
        with self._lock:
            bucket = self._buckets.get(client_ip)
            if bucket is not None:
                bucket.failed = 0


def _matches_bearer(header_value: Optional[str], expected: str) -> bool:
    if not header_value:
        return False
    parts = header_value.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    return constant_time_equal(parts[1], expected)


__all__ = [
    "RestAuthGate", "generate_token", "constant_time_equal",
]
