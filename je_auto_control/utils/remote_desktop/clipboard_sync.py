"""Serialization helpers for CLIPBOARD messages.

The wire format is a JSON envelope so adding new payload kinds (rich
text, file lists, ...) doesn't require touching the framing layer:

* ``{"kind": "text", "text": "..."}``
* ``{"kind": "image", "format": "png", "data_b64": "..."}``
"""
import base64
import json
from typing import Any, Dict, Tuple


class ClipboardSyncError(ValueError):
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
            return ("image", base64.b64decode(encoded))
        except (ValueError, TypeError) as error:
            raise ClipboardSyncError(
                f"invalid base64 image payload: {error}"
            ) from error
    raise ClipboardSyncError(f"unknown clipboard kind: {kind!r}")
