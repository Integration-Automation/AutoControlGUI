"""Network egress allowlist guard.

Unattended automation that can reach arbitrary hosts is an exfiltration risk.
``EgressPolicy`` lets an operator pin which hosts the headless HTTP client may
talk to: an **allow** list (default-deny — only matching hosts pass) and/or a
**deny** list (block these even if otherwise allowed). Patterns are case-
insensitive :mod:`fnmatch` globs over the URL hostname, e.g. ``*.example.com``
or ``localhost``.

A module-level :data:`default_policy` is consulted by
:func:`je_auto_control.utils.http_client.http_client.http_request`. It starts
in *allow-all* mode, so there is no behavior change until an operator calls
:func:`set_egress_policy`; once an allow list is set, egress is locked down.

Pure standard library; imports no ``PySide6``.
"""
import fnmatch
from typing import List, Optional, Sequence, Union
from urllib.parse import urlparse

Patterns = Optional[Union[str, Sequence[str]]]


def _as_patterns(value: Patterns) -> Optional[List[str]]:
    """Normalise ``None`` / a comma-string / an iterable to a lowercase list."""
    if value is None:
        return None
    items = value.split(",") if isinstance(value, str) else list(value)
    return [str(item).strip().lower() for item in items if str(item).strip()]


class EgressBlocked(ValueError):
    """Raised when a URL's host is not permitted by the egress policy."""


def _host_of(url: str) -> Optional[str]:
    """Return the lowercase hostname of ``url``, or ``None`` if absent."""
    host = urlparse(url).hostname
    return host.lower() if host else None


class EgressPolicy:
    """An allow/deny policy over outbound HTTP(S) hostnames."""

    def __init__(self, allow: Patterns = None, deny: Patterns = None) -> None:
        """``allow=None`` means allow-all; ``allow=[]`` means deny everything."""
        self._allow: Optional[List[str]] = None
        self._deny: List[str] = []
        self.configure(allow, deny)

    def configure(self, allow: Patterns = None, deny: Patterns = None) -> None:
        """Reset the allow/deny patterns in place (``allow=None`` is allow-all).

        Each list accepts a sequence of patterns or a single comma-separated
        string, so visual-builder and JSON-action inputs both work.
        """
        self._allow = _as_patterns(allow)
        self._deny = _as_patterns(deny) or []

    @property
    def allow(self) -> Optional[List[str]]:
        """The allow patterns (``None`` when unset / allow-all)."""
        return list(self._allow) if self._allow is not None else None

    @property
    def deny(self) -> List[str]:
        """The deny patterns."""
        return list(self._deny)

    @staticmethod
    def _matches(host: str, patterns: List[str]) -> bool:
        return any(fnmatch.fnmatch(host, pattern) for pattern in patterns)

    def is_allowed(self, url: str) -> bool:
        """Return whether ``url``'s host is permitted by this policy."""
        if self._allow is None and not self._deny:
            return True  # allow-all: no policy configured
        host = _host_of(url)
        if host is None:
            return False
        if self._matches(host, self._deny):
            return False
        if self._allow is None:
            return True  # deny-list-only mode
        return self._matches(host, self._allow)

    def check(self, url: str) -> None:
        """Raise :class:`EgressBlocked` if ``url``'s host is not permitted."""
        if not self.is_allowed(url):
            raise EgressBlocked(
                f"egress to {_host_of(url)!r} is blocked by the egress policy")


default_policy = EgressPolicy()


def get_egress_policy() -> EgressPolicy:
    """Return the module-level policy consulted by the HTTP client."""
    return default_policy


def set_egress_policy(allow: Patterns = None,
                      deny: Patterns = None) -> EgressPolicy:
    """Reconfigure the module-level policy; ``allow=None, deny=None`` is allow-all."""
    default_policy.configure(allow, deny)
    return default_policy
