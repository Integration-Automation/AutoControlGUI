"""RFC 3986 URL canonicalisation, normalisation and query helpers.

The ``egress`` policy only lowercases a URL's hostname for matching and
``http_client`` passes raw URLs straight to ``urllib``. Nothing lowercases the
scheme, removes a default port, collapses ``.``/``..`` path segments, normalises
percent-encoding case, or offers query build/parse/sort or URL-equality — the
primitives every crawler, cache key, allowlist match and link comparison needs.

Pure standard library (``urllib.parse``); imports no ``PySide6``.
Every function is pure (URL in, URL/bool/list out), so it is fully deterministic
in CI.
"""
import re
from typing import List, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443, "ftp": 21, "ws": 80, "wss": 443}
_PERCENT = re.compile(r"%[0-9a-fA-F]{2}")
QueryPairs = Sequence[Tuple[str, str]]


_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def _normalize_escape(escape: str) -> str:
    char = chr(int(escape[1:], 16))
    return char if char in _UNRESERVED else escape.upper()


def _normalize_percent(text: str) -> str:
    """Normalise every percent-escape (RFC 3986 §6.2.2.1 and §6.2.2.2).

    Hex digits are upper-cased, and an escape of an unreserved character
    (``%7E`` for ``~``) is decoded, since both spellings name the same URL.
    """
    return _PERCENT.sub(lambda match: _normalize_escape(match.group(0)), text)


def _lower_outside_escapes(text: str) -> str:
    """Lower-case ``text`` but keep the hex digits of its percent-escapes upper-case."""
    pieces = _PERCENT.split(text)
    escapes = _PERCENT.findall(text)
    return "".join(piece.lower() + (escapes[index] if index < len(escapes) else "")
                   for index, piece in enumerate(pieces))


def _remove_dot_segments(path: str) -> str:
    """RFC 3986 5.2.4: resolve ``.`` / ``..``; empty segments stay.

    ``posixpath.normpath`` dropped the trailing slash of ``/a/b/..`` and
    merged ``//`` -- both change which resource the URL names.
    """
    segments = path.split("/")
    out: List[str] = []
    for segment in segments:
        if segment == "..":
            if len(out) > 1 or (out and out[0]):
                out.pop()
        elif segment != ".":
            out.append(segment)
    if segments[-1] in (".", ".."):
        out.append("")
    return "/".join(out)


def _normalize_path(path: str, has_authority: bool) -> str:
    """Resolve dot segments; with an authority the path is absolute (``/``).

    Escapes are normalised first (RFC 3986 6.2.2.2 before 6.2.2.3): resolving
    first left ``/public/%2E%2E/admin`` as ``/public/../admin``, a traversal
    a ``/public/`` prefix allowlist accepted.
    """
    path = _normalize_percent(path)
    if not has_authority:
        # mailto:a@b has no authority and no leading slash to add.
        return _remove_dot_segments(path) if path.startswith("/") else path
    if not path:
        return "/"
    resolved = _remove_dot_segments(path)
    return resolved if resolved.startswith("/") else "/" + resolved


def _normalize_query(query: str, sort: bool) -> str:
    """Normalise percent-escape case, optionally sorting the pairs.

    Pairs are kept as written: decoding and re-encoding them turned a
    non-UTF-8 escape into U+FFFD and a bare key ``flag`` into ``flag=``.
    """
    # Normalised before sorting: ``k=%7A&k=b`` sorted as written and never
    # matched ``k=z&k=b``.
    pairs = _normalize_percent(query).split("&")
    if sort:
        pairs = sorted(pairs)
    return "&".join(pairs)


def _build_netloc(parts: SplitResult, host: str, scheme: str,
                  strip_default_port: bool) -> str:
    """Reassemble the authority, dropping a redundant default port."""
    # The raw userinfo: parts.username is "" for ":pw@h", which lost the
    # password, and the parsed fields are already percent-decoded.
    raw_userinfo, at, _ = parts.netloc.rpartition("@")
    userinfo = _normalize_percent(raw_userinfo) + at
    if ":" in host:
        host = f"[{host}]"  # hostname drops an IPv6 literal's brackets
    port = parts.port
    if (port is not None and strip_default_port
            and _DEFAULT_PORTS.get(scheme) == port):
        port = None
    netloc = userinfo + host
    if port is not None:
        netloc += f":{port}"
    return netloc


def _recompose(scheme: str, authority: Optional[str], path: str,
               query: Optional[str], fragment: Optional[str]) -> str:
    """RFC 3986 5.3 recomposition; a ``None`` component is absent, ``""`` is present but empty.

    ``urlunsplit`` dropped an empty ``?`` / ``#`` (``http://h/?`` is not
    ``http://h/``, 6.2.3), and a path that begins with ``//`` without an
    authority became one: ``http:/a/..//evil.com/`` came out as
    ``http://evil.com/`` or ``http:////evil.com/`` depending on the CPython
    version. Such a path is written ``/.//...``, as the WHATWG URL serializer does.
    """
    out = f"{scheme}:" if scheme else ""
    if authority is not None:
        out += "//" + authority
    elif path.startswith("//"):
        out += "/."
    out += path
    if query is not None:
        out += "?" + query
    if fragment is not None:
        out += "#" + fragment
    return out


def normalize_url(url: str, *, sort_query: bool = False,
                  strip_default_port: bool = True,
                  strip_fragment: bool = False) -> str:
    """Return a normalised form of ``url`` (RFC 3986 syntax-based)."""
    text = (url or "").strip()
    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    before_fragment, hash_sign, _ = text.partition("#")
    has_authority = (text[len(parts.scheme) + 1:] if parts.scheme else text).startswith("//")
    # hostname lower-cases escapes too; decode the unreserved ones, then lower the rest.
    host = _lower_outside_escapes(_normalize_percent(parts.hostname or ""))
    authority = _build_netloc(parts, host, scheme, strip_default_port) if has_authority else None
    path = _normalize_path(parts.path, has_authority)
    query = _normalize_query(parts.query, sort_query) if "?" in before_fragment else None
    fragment = None if strip_fragment or not hash_sign else _normalize_percent(parts.fragment)
    return _recompose(scheme, authority, path, query, fragment)


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
