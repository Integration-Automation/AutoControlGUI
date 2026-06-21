"""Conditional HTTP requests and RFC 9111 cache validators.

``http_request`` never sends ``If-None-Match`` / ``If-Modified-Since`` nor reads
``Cache-Control``, so every poll re-downloads an unchanged resource. This
extracts caching validators from a response, parses ``Cache-Control``, decides
freshness, and conditions the next request so the server can answer ``304 Not
Modified``.

Pure standard library; imports no ``PySide6``. Freshness takes an explicit age
(no wall clock), so the logic is fully deterministic in CI.
"""
from typing import Any, Dict, Mapping, Optional


def _header(headers: Optional[Mapping[str, Any]], name: str) -> str:
    for key, value in (headers or {}).items():
        if str(key).lower() == name:
            return str(value)
    return ""


def parse_cache_control(headers: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Parse a ``Cache-Control`` header into a directive dict."""
    directives: Dict[str, Any] = {}
    for part in _header(headers, "cache-control").split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        key, sep, value = cleaned.partition("=")
        name = key.strip().lower()
        if not sep:
            directives[name] = True
            continue
        token = value.strip().strip('"')
        try:
            directives[name] = int(token)
        except ValueError:
            directives[name] = token
    return directives


def store_validators(response: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract cache validators from an ``http_request`` response."""
    headers = response.get("headers") or {}
    return {"etag": _header(headers, "etag") or None,
            "last_modified": _header(headers, "last-modified") or None,
            "date": _header(headers, "date") or None,
            "cache_control": parse_cache_control(headers)}


def conditioned_call(call: Mapping[str, Any],
                     validators: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a copy of a ``build_call`` dict with conditional headers added."""
    headers = dict(call.get("headers") or {})
    if validators.get("etag"):
        headers["If-None-Match"] = validators["etag"]
    if validators.get("last_modified"):
        headers["If-Modified-Since"] = validators["last_modified"]
    out = dict(call)
    out["headers"] = headers
    return out


def is_fresh(validators: Mapping[str, Any], age_seconds: float) -> bool:
    """Whether a cached entry is still fresh ``age_seconds`` after storing."""
    cache_control = validators.get("cache_control") or {}
    if cache_control.get("no-store") or cache_control.get("no-cache"):
        return False
    max_age = cache_control.get("max-age")
    if isinstance(max_age, int):
        return age_seconds < max_age
    return False


def is_not_modified(response: Mapping[str, Any]) -> bool:
    """Whether ``response`` is a ``304 Not Modified``."""
    return int(response.get("status", 0)) == 304
