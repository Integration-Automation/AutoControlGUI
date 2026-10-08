"""Bearer-token auth + per-client rate-limit gate for the REST server.

Kept separate from ``rest_server`` so the auth policy can be unit-tested
without spinning up an HTTP server, and so future schemes (mTLS, HMAC,
OAuth) can plug in without touching dispatch code.

Token model:
  * Tokens are URL-safe random strings, ``_DEFAULT_TOKEN_BYTES`` of entropy.
  * Comparison uses :func:`secrets.compare_digest` to avoid timing leaks.
  * The token is generated once at server start and surfaced on the
    ``RestApiServer`` instance so the GUI / CLI can show it to the user.
  * With a ``user_store`` (opt-in RBAC) the shared token is not accepted at
    all: a bearer token must belong to one user of the store, and the gate
    hands back who that is so the server can authorise the route. One token
    that passed for everyone could not be told apart by role.

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
from typing import Dict, Optional, Tuple

from je_auto_control.utils.rbac.authorization import AuthorizationContext, resolve_token
from je_auto_control.utils.rbac.users import UserStore


_DEFAULT_TOKEN_BYTES = 24
_REQUESTS_PER_MINUTE = 120.0
_BURST = 30.0
_FAILED_AUTH_WINDOW_S = 60.0
_FAILED_AUTH_THRESHOLD = 8


def generate_token() -> str:
    """Return a fresh URL-safe random bearer token."""
    return secrets.token_urlsafe(_DEFAULT_TOKEN_BYTES)


def constant_time_equal(provided: str, expected: str) -> bool:
    """Timing-safe string compare; both args must be ``str``.

    Compared as UTF-8 bytes: ``compare_digest`` raises ``TypeError`` on a
    non-ASCII ``str``, and http.server decodes headers as latin-1, so a
    crafted token used to kill the request thread -- no response, and no
    failed attempt counted toward the lockout -- instead of being refused.
    """
    return secrets.compare_digest(provided.encode("utf-8"),
                                  expected.encode("utf-8"))


@dataclass
class _Bucket:
    tokens: float
    last_refill: float
    failed: int = 0
    failed_window_start: float = 0.0


@dataclass(frozen=True)
class AuthResult:
    """What the gate decided, and who the caller is when RBAC identified one."""

    verdict: str
    context: Optional[AuthorizationContext] = None


class RestAuthGate:
    """Bearer-token check + per-IP token bucket.

    ``authenticate(...)`` returns the verdict together with the caller's
    identity; ``check(...)`` returns the verdict alone -- one of ``"ok"``,
    ``"unauthorized"``, ``"rate_limited"``, ``"locked_out"``.
    """

    def __init__(self, expected_token: str,
                 *, requests_per_minute: float = _REQUESTS_PER_MINUTE,
                 burst: float = _BURST,
                 user_store: Optional[UserStore] = None) -> None:
        self._token = expected_token
        self._users = user_store
        self._rate_per_s = float(requests_per_minute) / 60.0
        self._burst = float(burst)
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    @property
    def expected_token(self) -> str:
        return self._token

    @property
    def rbac_enabled(self) -> bool:
        """``True`` when tokens are resolved through a user store."""
        return self._users is not None

    def check(self, *, client_ip: str, header_value: Optional[str]) -> str:
        """The verdict of :meth:`authenticate`, for callers that need no identity."""
        return self.authenticate(client_ip=client_ip, header_value=header_value).verdict

    def authenticate(self, *, client_ip: str,
                     header_value: Optional[str]) -> AuthResult:
        """Rate-limit, then authenticate; a valid token is never locked out.

        The lockout used to be checked first, keyed by IP alone -- and every
        local client is 127.0.0.1, every proxied one the proxy -- so eight bad
        requests a minute from anyone kept the real token holder out. It now
        only answers wrong tokens; the per-IP rate limit still applies to all.
        """
        if not self._consume_token(client_ip):
            return AuthResult("rate_limited")
        accepted, context = self._identify(header_value)
        if accepted:
            self._reset_failures(client_ip)
            return AuthResult("ok", context)
        if self._is_locked_out(client_ip):
            return AuthResult("locked_out")
        self._note_failure(client_ip)
        return AuthResult("unauthorized")

    def _identify(self, header_value: Optional[str],
                  ) -> Tuple[bool, Optional[AuthorizationContext]]:
        """``(accepted, caller)``; the caller is ``None`` under the shared token."""
        provided = _bearer_token(header_value)
        if provided is None:
            return False, None
        if self._users is None:
            return constant_time_equal(provided, self._token), None
        context = resolve_token(self._users, provided)
        return context is not None, context

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


def _bearer_token(header_value: Optional[str]) -> Optional[str]:
    """The token of an ``Authorization: Bearer <token>`` header, or ``None``."""
    if not header_value:
        return None
    parts = header_value.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


def _matches_bearer(header_value: Optional[str], expected: str) -> bool:
    provided = _bearer_token(header_value)
    return provided is not None and constant_time_equal(provided, expected)


__all__ = [
    "AuthResult", "RestAuthGate", "generate_token", "constant_time_equal",
]
