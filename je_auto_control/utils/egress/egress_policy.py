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
import ipaddress
import re
import socket
from typing import List, Optional, Sequence, Union
from urllib.parse import unquote, urlparse

from je_auto_control.utils.exception.exceptions import AutoControlException

Patterns = Optional[Union[str, Sequence[str]]]


def _as_patterns(value: Patterns) -> Optional[List[str]]:
    """Normalise ``None`` / a comma-string / an iterable to a lowercase list."""
    if value is None:
        return None
    items = value.split(",") if isinstance(value, str) else list(value)
    patterns = [_ascii_name(str(item).strip().lower().rstrip(".")) or str(item).strip().lower()
                for item in items]
    patterns = [pattern.rstrip(".") for pattern in patterns]
    return [_canonical_ip(pattern) or pattern for pattern in patterns if pattern]


def _ascii_name(host: str) -> Optional[str]:
    """The ASCII name a socket connects to for ``host`` (IDNA), or ``None``.

    IDNA drops a soft hyphen, folds fullwidth letters and digits and turns the
    ideographic full stop into a dot, so "12<SHY>7.0.0.1" and "evil<U+3002>com"
    reached 127.0.0.1 and evil.com while a deny list compared the raw text.
    """
    if host.isascii():
        return host
    try:
        return host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None


class EgressBlocked(AutoControlException, ValueError):
    """Raised when a URL's host is not permitted by the egress policy."""


_NUMERIC_HOST = re.compile(r"^[0-9a-fx.]+$")


def _host_of(url: str) -> Optional[str]:
    """Return the canonical hostname of ``url``, or ``None`` if absent.

    The literal hostname was matched, but urllib connects to the decoded
    one: ``%65vil.com`` reached ``evil.com``, ``evil.com.`` is the same host,
    and ``2130706433`` / ``0x7f.1`` / ``[::ffff:127.0.0.1]`` all name
    127.0.0.1 -- each walked past a deny list. Names are still matched as
    names; what they resolve to is not checked.
    """
    host = urlparse(url).hostname
    if not host:
        return None
    # A name IDNA cannot encode cannot be connected to either: no host, blocked.
    ascii_host = _ascii_name(unquote(host).lower())
    if ascii_host is None:
        return None
    host = ascii_host.rstrip(".")
    return _canonical_ip(host) or host or None


def _canonical_ip(host: str) -> Optional[str]:
    """Dotted-quad / compressed form of an IP literal in any spelling, else None."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not _NUMERIC_HOST.match(host):
            return None
        try:  # the legacy forms getaddrinfo accepts: 2130706433, 0x7f.1, 127.1
            address = ipaddress.ip_address(socket.inet_aton(host))
        except OSError:
            return None
    mapped = getattr(address, "ipv4_mapped", None)
    return str(mapped or address)


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
