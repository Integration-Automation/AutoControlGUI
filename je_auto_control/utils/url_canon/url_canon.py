"""RFC 3986 URL canonicalisation, normalisation and query helpers.

The ``egress`` policy only lowercases a URL's hostname for matching and
``http_client`` passes raw URLs straight to ``urllib``. Nothing lowercases the
scheme, removes a default port, collapses ``.``/``..`` path segments, normalises
percent-encoding case, or offers query build/parse/sort or URL-equality — the
primitives every crawler, cache key, allowlist match and link comparison needs.

Pure standard library (``urllib.parse`` + ``posixpath``); imports no ``PySide6``.
Every function is pure (URL in, URL/bool/list out), so it is fully deterministic
in CI.
"""
import posixpath
import re
from typing import List, Mapping, Sequence, Tuple, Union
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443, "ftp": 21, "ws": 80, "wss": 443}
_PERCENT = re.compile(r"%[0-9a-fA-F]{2}")
QueryPairs = Sequence[Tuple[str, str]]


def _normalize_percent(text: str) -> str:
    """Upper-case the hex digits of every percent-escape (RFC 3986 §6.2.2.1)."""
    return _PERCENT.sub(lambda match: match.group(0).upper(), text)


def _normalize_path(path: str) -> str:
    """Collapse ``.``/``..`` segments and guarantee a leading slash."""
    if not path:
        return "/"
    collapsed = posixpath.normpath(path)
    if path.endswith("/") and not collapsed.endswith("/"):
        collapsed += "/"
    if not collapsed.startswith("/"):
        collapsed = "/" + collapsed
    return _normalize_percent(collapsed)


def _build_netloc(parts: "urlsplit", host: str, scheme: str,
                  strip_default_port: bool) -> str:
    """Reassemble the authority, dropping a redundant default port."""
    userinfo = ""
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo += ":" + parts.password
        userinfo += "@"
    port = parts.port
    if (port is not None and strip_default_port
            and _DEFAULT_PORTS.get(scheme) == port):
        port = None
    netloc = userinfo + host
    if port is not None:
        netloc += f":{port}"
    return netloc


def normalize_url(url: str, *, sort_query: bool = False,
                  strip_default_port: bool = True,
                  strip_fragment: bool = False) -> str:
    """Return a normalised form of ``url`` (RFC 3986 syntax-based)."""
    parts = urlsplit((url or "").strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    netloc = _build_netloc(parts, host, scheme, strip_default_port)
    path = _normalize_path(parts.path) if netloc or parts.path else parts.path
    query = parts.query
    if query:
        pairs = parse_qsl(query, keep_blank_values=True)
        if sort_query:
            pairs = sorted(pairs)
        query = _normalize_percent(urlencode(pairs))
    fragment = "" if strip_fragment else parts.fragment
    return urlunsplit((scheme, netloc, path, query, fragment))


def canonicalize_url(url: str) -> str:
    """Return the opinionated canonical form for equality / de-duplication.

    Sorts the query, drops the default port and the fragment on top of
    :func:`normalize_url`.
    """
    return normalize_url(url, sort_query=True, strip_default_port=True,
                         strip_fragment=True)


def urls_equal(first: str, second: str) -> bool:
    """Whether two URLs are equivalent after canonicalisation."""
    return canonicalize_url(first) == canonicalize_url(second)


def build_query(params: Union[Mapping[str, object], QueryPairs], *,
                sort: bool = False, doseq: bool = True) -> str:
    """Encode a mapping or pair-list into a query string."""
    items: List[Tuple[str, object]] = (list(params.items())
                                       if isinstance(params, Mapping)
                                       else list(params))
    if sort:
        items = sorted(items, key=lambda kv: (kv[0], str(kv[1])))
    return urlencode(items, doseq=doseq)


def parse_query(query: str, *, keep_blank: bool = True) -> List[Tuple[str, str]]:
    """Parse a query string into an ordered list of ``(key, value)`` pairs."""
    return parse_qsl(query or "", keep_blank_values=keep_blank)
