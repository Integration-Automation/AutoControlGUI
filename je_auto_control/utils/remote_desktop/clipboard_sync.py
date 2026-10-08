"""Serialization helpers for CLIPBOARD messages.

The wire format is a JSON envelope so adding new payload kinds (rich
text, file lists, ...) doesn't require touching the framing layer:

* ``{"kind": "text", "text": "..."}``
* ``{"kind": "image", "format": "png", "data_b64": "..."}``

Applying a peer's clipboard changes the local clipboard, which a watcher
then sees as a change and sends back -- and the peer does the same.
:class:`ClipboardEchoGuard` breaks that loop for any code that forwards
clipboard changes automatically. ``RemoteDesktopHost`` keeps one per
connected viewer and ``RemoteDesktopViewer`` one for its host: receiving a
CLIPBOARD message notes it, and ``broadcast_clipboard_*`` /
``send_clipboard_*`` consult the guard when called with ``automatic=True``.
"""
import base64
import hashlib
import json
import threading
from typing import Any, Dict, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException


class ClipboardSyncError(AutoControlException, ValueError):
    """Raised when a CLIPBOARD payload is malformed or unsupported."""


def _fingerprint(kind: str, data: Any) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    return f"{kind}:{hashlib.sha256(raw).hexdigest()}"


class ClipboardEchoGuard:
    """Decides whether a local clipboard change should be sent to the peer.

    Call :meth:`note_remote` with what was just applied from the peer, and
    ask :meth:`should_send` before forwarding a local change;
    :meth:`note_sent` records a send that was made without asking (a person
    pressing "send clipboard"). Content that
    is exactly what the peer last sent is not sent back, and content already
    sent is not sent again while the clipboard still holds it, so two
    machines watching each other's clipboard settle after one transfer
    instead of bouncing it forever. Only fingerprints are kept, never the
    clipboard content.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._from_remote: Optional[str] = None
        self._sent: Optional[str] = None

    def note_remote(self, kind: str, data: Any) -> None:
        """Record content that arrived from the peer and was applied locally."""
        with self._lock:
            self._from_remote = _fingerprint(kind, data)

    def note_sent(self, kind: str, data: Any) -> None:
        """Record content that was sent to the peer without asking the guard."""
        with self._lock:
            self._sent = _fingerprint(kind, data)

    def should_send(self, kind: str, data: Any) -> bool:
        """Whether this local clipboard content is news to the peer.

        Returning ``True`` records the content as sent.
        """
        fingerprint = _fingerprint(kind, data)
        with self._lock:
            if fingerprint in (self._from_remote, self._sent):
                return False
            self._sent = fingerprint
            return True

    def reset(self) -> None:
        """Forget both sides (after a reconnect: the peer may hold anything)."""
        with self._lock:
            self._from_remote = None
            self._sent = None


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
