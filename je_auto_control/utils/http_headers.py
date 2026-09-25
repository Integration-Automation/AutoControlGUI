"""Shared, defensive helpers for this package's servers: headers, bodies, replies, logs.

``http.server`` does not validate header values, so a client is free to send
``Content-Length: abc``. Every server in this package read it with a bare
``int(...)``, which raised ValueError *inside the handler thread*: the thread
died and the connection was closed with no response at all — the client saw a
reset instead of the 400 each server already had code to send.
"""
import json
from typing import Any, Callable, Optional, Protocol

from je_auto_control.utils.exception.exceptions import AutoControlException

# Sentinel for "the client did not give us a usable length". It is negative on
# purpose: every caller already rejects non-positive lengths, so an
# unparseable header flows into the exact same branch as a missing one and
# each server keeps its own policy (400, or an empty body).
INVALID_CONTENT_LENGTH = -1


class HeaderLookup(Protocol):
    """Anything that answers ``get(name)`` for one HTTP header.

    Deliberately not ``Mapping[str, str]``: ``http.server`` hands each
    handler an ``email.message.Message``, which is not a mapping over its
    keys and which matches header names case-insensitively — the property
    that makes ``Content-length`` work. Every caller here passes that.
    """

    def get(self, name: str, /) -> Any:
        """Return the header's value, or ``None`` when it is absent."""


def parse_content_length(headers: HeaderLookup) -> int:
    """Return the request's Content-Length, or ``INVALID_CONTENT_LENGTH``.

    Never raises: a malformed, signed, or absent header yields the sentinel.
    The value must be ASCII digits (RFC 9110 ``1*DIGIT``): ``int()`` alone
    also takes ``+5``, ``1_000`` and non-ASCII digits, which a proxy in
    front of the server may read differently.
    """
    raw = headers.get("Content-Length")
    if raw is None or str(raw).strip() == "":
        return 0
    text = str(raw).strip()
    if not (text.isascii() and text.isdigit()) or _has_conflicting_copy(headers, int(text)):
        return INVALID_CONTENT_LENGTH
    return int(text)


def _has_conflicting_copy(headers: HeaderLookup, length: int) -> bool:
    """Whether another Content-Length header disagrees with the first.

    RFC 9112 6.3 makes such a message's framing invalid: ``get`` returns the
    first copy only, and a proxy that honours the second one splits the
    stream somewhere else (request smuggling). Identical copies are fine.
    """
    get_all = getattr(headers, "get_all", None)
    if get_all is None:
        return False
    for value in get_all("Content-Length") or ():
        other = str(value).strip()
        if not (other.isascii() and other.isdigit()) or int(other) != length:
            return True
    return False


#: C0 and C1 controls, and the backslash that escapes them, written as
#: ``BaseHTTPRequestHandler.log_message`` writes them since Python 3.12.
_LOG_ESCAPES = {code: fr"\x{code:02x}" for code in (*range(0x20), *range(0x7F, 0xA0))}
_LOG_ESCAPES[ord("\\")] = r"\\"
_LOG_TABLE = str.maketrans(_LOG_ESCAPES)


def log_safe(text: str) -> str:
    """``text`` with its control characters escaped, for one access-log line.

    The stdlib's ``log_message`` escapes the request line; every server here
    overrides it, so a client could write a carriage return, a terminal
    escape sequence or a fake log line into the log before it authenticated.
    """
    return text.translate(_LOG_TABLE)


def wire_json_text(value: Any, *, default: Optional[Callable[[Any], Any]] = None) -> str:
    """``value`` as JSON text that always encodes as UTF-8.

    Non-ASCII text stays as it is unless the value holds a lone surrogate (a
    file name read with ``surrogateescape``, say). UTF-8 cannot encode that,
    so the reply was never sent and the connection dropped; the text is then
    ASCII-escaped as a whole, which JSON readers decode to the same value.
    Raises what ``json.dumps`` raises for a value it cannot serialise.
    """
    text = json.dumps(value, ensure_ascii=False, default=default)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return json.dumps(value, ensure_ascii=True, default=default)
    return text


def bearer_challenge(realm: str, authorization: Optional[str]) -> str:
    """The ``WWW-Authenticate`` value a 401 must carry (RFC 9110 15.5.2, RFC 6750 3).

    ``error="invalid_token"`` only when a Bearer token was sent; a request
    with none, or with another scheme, gets the bare challenge.
    """
    scheme = str(authorization or "").strip().partition(" ")[0]
    if scheme.lower() == "bearer":
        return f'Bearer realm="{realm}", error="invalid_token"'
    return f'Bearer realm="{realm}"'


#: Headers whose values are credentials (lower case): stripped from a redirect
#: to another origin, masked in logs and never written to a cassette.
CREDENTIAL_HEADERS = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "x-auth-token",
})

#: Longest chunk-size or trailer line accepted, and most trailer lines.
_MAX_CHUNK_LINE = 1024
_MAX_TRAILERS = 64


class BodyReader(Protocol):
    """The part of a request's ``rfile`` a body reader uses."""

    def read(self, size: int = ..., /) -> bytes:
        """Read up to ``size`` bytes."""

    def readline(self, size: int = ..., /) -> bytes:
        """Read one line of at most ``size`` bytes."""


class ChunkedBodyError(AutoControlException):
    """A ``Transfer-Encoding: chunked`` body that is malformed or too large."""

    def __init__(self, message: str, too_large: bool = False) -> None:
        super().__init__(message)
        self.too_large = too_large


def is_chunked(headers: HeaderLookup) -> bool:
    """Whether the request body is sent with ``Transfer-Encoding: chunked``.

    Such a request has no Content-Length, so a server that only reads that
    header sees an empty body -- and answers 200 for data it never read.
    ``chunked`` has to be the final transfer coding (RFC 9112 6.1); a token
    that merely contains the word, such as ``xchunked``, is not it.
    """
    codings = str(headers.get("Transfer-Encoding") or "").split(",")
    return codings[-1].strip().lower() == "chunked"


def read_chunked_body(rfile: BodyReader, limit: int) -> bytes:
    """Decode a chunked request body from ``rfile``, refusing more than ``limit`` bytes.

    Raises :class:`ChunkedBodyError` (``too_large`` set for the limit) on a
    malformed or truncated stream. Trailer fields are read and discarded.
    """
    body = bytearray()
    while True:
        size = _chunk_size(rfile.readline(_MAX_CHUNK_LINE + 1))
        if size == 0:
            _skip_trailers(rfile)
            return bytes(body)
        if len(body) + size > limit:
            raise ChunkedBodyError("chunked body too large", too_large=True)
        chunk = rfile.read(size)
        if len(chunk) != size or rfile.readline(_MAX_CHUNK_LINE + 1).strip():
            raise ChunkedBodyError("truncated chunk")
        body += chunk


def _chunk_size(line: bytes) -> int:
    if len(line) > _MAX_CHUNK_LINE or not line.endswith(b"\n"):
        raise ChunkedBodyError("malformed chunk-size line")
    token = line.split(b";", 1)[0].strip()
    if not token or token.lstrip(b"0123456789abcdefABCDEF"):
        raise ChunkedBodyError("malformed chunk size")
    return int(token, 16)


def _skip_trailers(rfile: BodyReader) -> None:
    for _ in range(_MAX_TRAILERS):
        if rfile.readline(_MAX_CHUNK_LINE + 1) in (b"\r\n", b"\n", b""):
            return
    raise ChunkedBodyError("too many trailer fields")
