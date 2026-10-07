"""Bounded opaque per-view cursor signatures; payloads never confer tool permissions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json


from je_auto_control.utils.exception.exceptions import AutoControlException


class InvalidCursorError(AutoControlException, ValueError):
    """A malformed or foreign per-view cursor signature/payload."""


class CursorSigner:
    """Authenticate snapshot/offset cursors with a secret belonging to one view."""

    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    def encode(self, snapshot_id: str, offset: int) -> str:
        """Encode a snapshot position; callers must treat the result as opaque."""
        payload = json.dumps([snapshot_id, offset], separators=(',', ':')).encode('ascii')
        tag = hmac.digest(self._secret, payload, hashlib.sha256)
        return base64.urlsafe_b64encode(tag + payload).decode('ascii')

    def decode(self, cursor: str) -> tuple[str, int]:
        """Reject malformed, changed and foreign cursors before looking up their snapshot."""
        if not isinstance(cursor, str) or not cursor or len(cursor) > 512:
            raise InvalidCursorError('invalid cursor')
        try:
            blob = base64.b64decode(cursor.encode('ascii'), altchars=b'-_', validate=True)
            tag, payload = blob[:32], blob[32:]
            if not hmac.compare_digest(tag, hmac.digest(self._secret, payload, hashlib.sha256)):
                raise InvalidCursorError('invalid cursor')
            row = json.loads(payload)
        except (ValueError, UnicodeError) as error:
            raise InvalidCursorError('invalid cursor') from error
        return _position(row)


def _position(row: object) -> tuple[str, int]:
    """Validate the signed payload shape independently of wire decoding."""
    if not isinstance(row, list) or len(row) != 2:
        raise InvalidCursorError('invalid cursor')
    identifier, offset = row
    if not isinstance(identifier, str) or isinstance(offset, bool) or not isinstance(offset, int) or offset < 1:
        raise InvalidCursorError('invalid cursor')
    return identifier, offset
