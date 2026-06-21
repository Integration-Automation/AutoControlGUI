"""A small RFC 6265 cookie jar for carrying a session across HTTP calls.

``http_request`` is stateless — no session cookies persist across calls, so a
login-then-call REST flow could not carry a session headlessly. This parses
``Set-Cookie`` response headers into a jar and builds the ``Cookie`` request
header; the jar is JSON-serialisable so a session can be saved and reloaded.

Pure standard library (``json``); imports no ``PySide6``. The jar is a simple
in-memory name-value store (cookies cleared on ``max-age<=0`` / empty value), so
behaviour is fully deterministic in CI.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

SetCookie = Union[str, List[str]]


def parse_set_cookie(header: str) -> Optional[Dict[str, Any]]:
    """Parse one ``Set-Cookie`` value into ``{name, value, attributes}``."""
    segments = [segment.strip() for segment in (header or "").split(";")]
    if not segments or "=" not in segments[0]:
        return None
    name, _, value = segments[0].partition("=")
    attributes: Dict[str, str] = {}
    for segment in segments[1:]:
        key, sep, attr_value = segment.partition("=")
        attributes[key.strip().lower()] = attr_value.strip() if sep else ""
    return {"name": name.strip(), "value": value.strip(),
            "attributes": attributes}


def _is_expired(attributes: Dict[str, str]) -> bool:
    max_age = attributes.get("max-age")
    if max_age is not None:
        try:
            return int(max_age) <= 0
        except ValueError:
            return False
    return False


class CookieJar:
    """An in-memory name-value cookie jar (RFC 6265, simplified)."""

    def __init__(self, cookies: Optional[Dict[str, str]] = None) -> None:
        self._cookies: Dict[str, str] = dict(cookies or {})

    def update(self, set_cookie: SetCookie) -> "CookieJar":
        """Apply one or more ``Set-Cookie`` headers to the jar."""
        headers = [set_cookie] if isinstance(set_cookie, str) else set_cookie
        for header in headers:
            self._apply_one(header)
        return self

    def _apply_one(self, header: str) -> None:
        parsed = parse_set_cookie(header)
        if parsed is None:
            return
        if not parsed["value"] or _is_expired(parsed["attributes"]):
            self._cookies.pop(parsed["name"], None)
        else:
            self._cookies[parsed["name"]] = parsed["value"]

    def set(self, name: str, value: str) -> "CookieJar":
        """Set a cookie value directly."""
        self._cookies[str(name)] = str(value)
        return self

    def cookie_header(self) -> str:
        """Build the ``Cookie`` request header value from stored cookies."""
        return "; ".join(f"{name}={value}"
                         for name, value in self._cookies.items())

    def to_dict(self) -> Dict[str, str]:
        """Return the stored cookies as a plain dict."""
        return dict(self._cookies)

    def __len__(self) -> int:
        return len(self._cookies)

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "CookieJar":
        """Build a jar from a plain ``{name: value}`` dict."""
        return cls(data)

    def save(self, path: str) -> str:
        """Persist the jar to ``path`` as JSON; return the path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self._cookies, indent=2), encoding="utf-8")
        return str(out)

    @classmethod
    def load(cls, path: str) -> "CookieJar":
        """Load a jar from a JSON file."""
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))
