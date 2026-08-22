"""Shared, defensive parsing for inbound HTTP headers.

``http.server`` does not validate header values, so a client is free to send
``Content-Length: abc``. Every server in this package read it with a bare
``int(...)``, which raised ValueError *inside the handler thread*: the thread
died and the connection was closed with no response at all — the client saw a
reset instead of the 400 each server already had code to send.
"""
from typing import Any, Protocol

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
