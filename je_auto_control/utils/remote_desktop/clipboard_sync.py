"""Serialization helpers for CLIPBOARD messages.

The wire format is a JSON envelope so adding new payload kinds (rich
text, file lists, ...) doesn't require touching the framing layer:

* ``{"kind": "text", "text": "..."}``
* ``{"kind": "image", "format": "png", "data_b64": "..."}``
"""
import base64
import hashlib
import json
import threading
import uuid
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException


class ClipboardSyncError(AutoControlException, ValueError):
    """Raised when a CLIPBOARD payload is malformed or unsupported."""


def encode_text(text: str) -> bytes:
    """Encode a text-clipboard payload."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return json.dumps(
        {"kind": "text", "text": text}, ensure_ascii=False,
    ).encode("utf-8")


def encode_image(png_bytes: bytes) -> bytes:
    """Encode a PNG image as a clipboard payload."""
    if not isinstance(png_bytes, (bytes, bytearray)):
        raise TypeError("png_bytes must be bytes")
    if not png_bytes:
        raise ValueError("png_bytes is empty")
    return json.dumps({
        "kind": "image",
        "format": "png",
        "data_b64": base64.b64encode(bytes(png_bytes)).decode("ascii"),
    }, ensure_ascii=False).encode("utf-8")


def decode(payload: bytes) -> Tuple[str, Any]:
    """Parse a CLIPBOARD payload; return ``(kind, data)``.

    For ``"text"`` ``data`` is a ``str``; for ``"image"`` it is the raw
    PNG bytes (already base64-decoded).
    """
    try:
        envelope: Dict[str, Any] = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ClipboardSyncError(f"invalid CLIPBOARD JSON: {error}") from error
    if not isinstance(envelope, dict):
        raise ClipboardSyncError("CLIPBOARD payload must be a JSON object")
    kind = envelope.get("kind")
    if kind == "text":
        text = envelope.get("text")
        if not isinstance(text, str):
            raise ClipboardSyncError("text payload missing 'text' string")
        return ("text", text)
    if kind == "image":
        if envelope.get("format") != "png":
            raise ClipboardSyncError(
                f"image format {envelope.get('format')!r} not supported"
            )
        encoded = envelope.get("data_b64", "")
        if not isinstance(encoded, str):
            raise ClipboardSyncError("image payload missing 'data_b64'")
        try:
            return ("image", base64.b64decode(encoded, validate=True))
        except (ValueError, TypeError) as error:
            raise ClipboardSyncError(
                f"invalid base64 image payload: {error}"
            ) from error
    raise ClipboardSyncError(f"unknown clipboard kind: {kind!r}")


class ClipboardLoopGuard:
    """Bounded per-session deduplication and one-send suppression of received clipboard content."""

    def __init__(self, *, origin: Optional[str] = None) -> None:
        self.origin = origin or uuid.uuid4().hex
        self._seen: Deque[str] = deque(maxlen=256)
        self._echo: Optional[str] = None
        self._lock = threading.Lock()

    @staticmethod
    def _identity(kind: str, value: Any) -> str:
        data = value.encode('utf-8') if isinstance(value, str) else bytes(value)
        return hashlib.sha256(kind.encode('ascii') + b'\0' + data).hexdigest()

    def _encode(self, payload: bytes) -> Optional[bytes]:
        kind, value = decode(payload)
        digest = self._identity(kind, value)
        with self._lock:
            if digest == self._echo:
                self._echo = None
                return None
            envelope = json.loads(payload)
            envelope['sync'] = {'origin': self.origin, 'event': uuid.uuid4().hex, 'sha256': digest}
            return json.dumps(envelope, ensure_ascii=False).encode('utf-8')

    def encode_text(self, text: str) -> Optional[bytes]:
        """Encode a text event, or consume suppression of the last received value."""
        return self._encode(encode_text(text))

    def encode_image(self, png_bytes: bytes) -> Optional[bytes]:
        """Encode an image event, or consume suppression of the last received image."""
        return self._encode(encode_image(png_bytes))

    def receive(self, payload: bytes) -> Optional[Tuple[str, Any]]:
        """Decode old/new envelopes; reject malformed identities and drop received duplicates."""
        kind, value = decode(payload)
        digest = self._identity(kind, value)
        metadata = json.loads(payload).get('sync')
        if metadata is None:
            identity = 'legacy:' + digest
        else:
            if not isinstance(metadata, dict) or metadata.get('sha256') != digest:
                raise ClipboardSyncError('invalid clipboard sync identity')
            if not all(isinstance(metadata.get(key), str) and metadata[key] for key in ('origin', 'event')):
                raise ClipboardSyncError('invalid clipboard sync identity')
            if metadata['origin'] == self.origin:
                return None
            identity = metadata['origin'] + ':' + metadata['event']
        with self._lock:
            if identity in self._seen:
                return None
            self._seen.append(identity)
            self._echo = digest
        return kind, value
