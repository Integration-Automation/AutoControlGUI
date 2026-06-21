"""HTTP content negotiation and transparent response decompression.

``urllib`` / ``http_request`` never sets ``Accept-Encoding`` and never decodes a
``Content-Encoding`` response, so a body from a server that compresses arrives
raw; there was also no quality-value parser. This adds ``Accept`` /
``Accept-Encoding`` builders, a q-value parser, and gzip / deflate decoding.

Pure standard library (``gzip`` / ``zlib``); imports no ``PySide6``. Brotli is
deliberately excluded (not stdlib). Every function is pure, so it is fully
deterministic in CI.
"""
import gzip
import zlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

AcceptEntry = Union[str, Tuple[str, float]]
_DEFAULT_ENCODINGS = ("gzip", "deflate")


def build_accept(types: Sequence[AcceptEntry]) -> str:
    """Build an ``Accept`` header from media types or ``(type, q)`` pairs."""
    parts: List[str] = []
    for entry in types:
        if isinstance(entry, (tuple, list)):
            media, quality = entry[0], float(entry[1])
            parts.append(media if quality >= 1.0 else f"{media};q={quality}")
        else:
            parts.append(entry)
    return ", ".join(parts)


def build_accept_encoding(encodings: Optional[Sequence[str]] = None) -> str:
    """Build an ``Accept-Encoding`` header (default ``gzip, deflate``)."""
    return ", ".join(encodings if encodings is not None else _DEFAULT_ENCODINGS)


def _quality_of(params: str) -> float:
    for param in params.split(";"):
        key, sep, value = param.partition("=")
        if sep and key.strip() == "q":
            try:
                return float(value.strip())
            except ValueError:
                return 0.0
    return 1.0


def parse_quality_values(header: Optional[str]) -> List[Tuple[str, float]]:
    """Parse a quality-value header into ``(token, q)`` sorted by ``q`` desc."""
    items: List[Tuple[str, float]] = []
    for part in (header or "").split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        token, _, params = cleaned.partition(";")
        items.append((token.strip(), _quality_of(params)))
    items.sort(key=lambda entry: -entry[1])      # stable: ties keep order
    return items


def _content_encoding(headers: Optional[Mapping[str, Any]]) -> str:
    for key, value in (headers or {}).items():
        if str(key).lower() == "content-encoding":
            return str(value).strip().lower()
    return ""


def decode_body(headers: Optional[Mapping[str, Any]], raw: bytes) -> bytes:
    """Decode ``raw`` per the response ``Content-Encoding`` header."""
    encoding = _content_encoding(headers)
    if encoding in ("", "identity"):
        return raw
    if encoding == "gzip":
        return gzip.decompress(raw)
    if encoding == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)   # raw deflate stream
    raise ValueError(f"unsupported content-encoding: {encoding!r}")


def negotiated_call(call: Mapping[str, Any], *, accept: Optional[str] = None,
                    accept_encoding: str = "gzip, deflate") -> Dict[str, Any]:
    """Return a copy of a ``build_call`` dict with negotiation headers set."""
    headers = dict(call.get("headers") or {})
    if accept:
        headers["Accept"] = accept
    if accept_encoding:
        headers["Accept-Encoding"] = accept_encoding
    out = dict(call)
    out["headers"] = headers
    return out
