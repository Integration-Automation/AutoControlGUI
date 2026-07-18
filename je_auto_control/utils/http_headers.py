"""Shared, defensive parsing for inbound HTTP headers.

``http.server`` does not validate header values, so a client is free to send
``Content-Length: abc``. Every server in this package read it with a bare
``int(...)``, which raised ValueError *inside the handler thread*: the thread
died and the connection was closed with no response at all — the client saw a
reset instead of the 400 each server already had code to send.
"""
from typing import Mapping

# Sentinel for "the client did not give us a usable length". It is negative on
# purpose: every caller already rejects non-positive lengths, so an
# unparseable header flows into the exact same branch as a missing one and
# each server keeps its own policy (400, or an empty body).
INVALID_CONTENT_LENGTH = -1


def parse_content_length(headers: Mapping[str, str]) -> int:
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
