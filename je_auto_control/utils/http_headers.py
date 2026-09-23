"""Shared, defensive parsing for inbound HTTP headers and chunked bodies.

``http.server`` does not validate header values, so a client is free to send
``Content-Length: abc``. Every server in this package read it with a bare
``int(...)``, which raised ValueError *inside the handler thread*: the thread
died and the connection was closed with no response at all — the client saw a
reset instead of the 400 each server already had code to send.
"""
from typing import Any, Protocol

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

    Never raises: a malformed, negative, or absent header yields the sentinel.
    """
    raw = headers.get("Content-Length")
    if raw is None or str(raw).strip() == "":
        return 0
    try:
        length = int(str(raw).strip())
    except (TypeError, ValueError):
        return INVALID_CONTENT_LENGTH
    # A negative length is as unusable as a malformed one; normalise so
    # callers only ever have to test `<= 0`.
    return length if length >= 0 else INVALID_CONTENT_LENGTH


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
    """
    return "chunked" in str(headers.get("Transfer-Encoding") or "").lower()


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
