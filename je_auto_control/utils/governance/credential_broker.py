"""Just-in-time credential leases — zero standing privilege for secrets.

Instead of handing automation a long-lived secret, a consumer takes a
*lease*: a short-lived token bound to a secret name with an expiry. The real
value is fetched only at :meth:`CredentialBroker.redeem` time, only while the
lease is valid, through a pluggable *resolver* (e.g. an unlocked
:class:`~je_auto_control.utils.secrets.secret_store.SecretManager`'s ``get``,
or an environment lookup). Expired or revoked leases yield nothing.

Secret values never enter executor/MCP records: the executor surface manages
the lease *lifecycle* only (``AC_lease_secret`` / ``AC_lease_valid`` /
``AC_revoke_lease`` / ``AC_lease_active``). :meth:`redeem`, which returns the
real value, is a deliberate Python-API-only escape hatch for code that must
handle the secret.

Pure standard library; imports no ``PySide6``. Clock and resolver are
injectable, so expiry is deterministically testable without real time or a
real vault.
"""
import math
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException


class CredentialBrokerError(AutoControlException, RuntimeError):
    """Raised when a lease is unknown/expired or no resolver is configured."""


class CredentialBroker:
    """Issues short-lived leases that resolve to secrets just in time."""

    def __init__(self,
                 resolver: Optional[Callable[[str], Optional[str]]] = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        """``resolver(name)`` returns the secret value; ``clock`` returns now."""
        self._resolver = resolver
        self._clock = clock
        self._leases: Dict[str, Dict[str, Any]] = {}
        # default_broker is shared by every thread; active() iterating while
        # another thread leased raised "dictionary changed size".
        self._lock = threading.Lock()

    def set_resolver(self, resolver: Callable[[str], Optional[str]]) -> None:
        """Configure the function that maps a secret name to its value."""
        self._resolver = resolver

    def lease(self, name: str, ttl: float = 300.0) -> str:
        """Issue a lease for secret ``name`` valid for ``ttl`` seconds.

        ``ttl`` must be a finite positive number: NaN never compared as
        expired, so such a lease was valid forever.
        """
        lifetime = float(ttl)
        if not math.isfinite(lifetime) or lifetime <= 0:
            raise CredentialBrokerError(f"lease ttl must be a positive number, got {ttl!r}")
        token = secrets.token_hex(8)
        with self._lock:
            self._leases[token] = {"name": name,
                                   "expires_at": self._clock() + lifetime}
        return token

    def _valid_lease(self, token: str) -> Optional[Dict[str, object]]:
        with self._lock:
            lease = self._leases.get(token)
            if lease is None:
                return None
            if self._clock() >= float(lease["expires_at"]):
                self._leases.pop(token, None)  # opportunistic expiry cleanup
                return None
            return lease

    def is_valid(self, token: str) -> bool:
        """Return ``True`` while ``token``'s lease exists and has not expired."""
        return self._valid_lease(token) is not None

    def redeem(self, token: str) -> str:
        """Return the secret value for a valid lease (Python-only by design).

        Raises :class:`CredentialBrokerError` if the lease is unknown/expired
        or no resolver is configured.
        """
        lease = self._valid_lease(token)
        if lease is None:
            raise CredentialBrokerError("lease is unknown or expired")
        if self._resolver is None:
            raise CredentialBrokerError("no secret resolver configured")
        value = self._resolver(str(lease["name"]))
        if value is None:
            raise CredentialBrokerError(
                f"resolver returned no value for {lease['name']!r}")
        return value

    def revoke(self, token: str) -> bool:
        """Revoke ``token`` immediately; return whether it existed."""
        with self._lock:
            return self._leases.pop(token, None) is not None

    def active(self) -> List[Dict[str, object]]:
        """List non-expired leases as ``{token, name, ttl_remaining}`` (no values)."""
        now = self._clock()
        result: List[Dict[str, object]] = []
        with self._lock:
            for token, lease in list(self._leases.items()):
                remaining = float(lease["expires_at"]) - now
                if remaining > 0:
                    result.append({"token": token, "name": lease["name"],
                                   "ttl_remaining": remaining})
                else:
                    self._leases.pop(token, None)
        return result


default_broker = CredentialBroker()


def set_secret_resolver(resolver: Callable[[str], Optional[str]]) -> None:
    """Configure the resolver used by the module-level :data:`default_broker`."""
    default_broker.set_resolver(resolver)
