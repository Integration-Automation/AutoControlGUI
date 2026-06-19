"""Perform HTTP(S) requests headlessly for first-class API action steps.

A small, dependency-free client built on the standard library, so the
package needs no ``requests`` dependency. Supports method, headers, a JSON
or raw body, basic/bearer auth, and an explicit timeout; it returns a
plain response dict (status / ok / headers / text / json / url) so that
non-2xx responses are inspectable rather than raised. Imports no
``PySide6`` and only allows http/https schemes (Bandit B310).
"""
import base64
import json
import urllib.error
import urllib.request
from typing import Any, Dict, Mapping, Optional

# NOSONAR python:S5332 — http is allow-listed deliberately (other schemes
# are rejected); plain http is required for internal/localhost endpoints.
_ALLOWED_SCHEMES = ("http://", "https://")  # NOSONAR python:S5332
_DEFAULT_TIMEOUT = 30.0


def _validate_url(url: str) -> None:
    if not isinstance(url, str) or not url.lower().startswith(_ALLOWED_SCHEMES):
        raise ValueError(f"only http/https URLs are allowed, got {url!r}")


def _apply_auth(headers: Dict[str, str],
                auth: Optional[Mapping[str, Any]]) -> None:
    if not auth:
        return
    kind = str(auth.get("type", "")).lower()
    if kind == "bearer":
        headers["Authorization"] = f"Bearer {auth.get('token', '')}"
    elif kind == "basic":
        raw = f"{auth.get('username', '')}:{auth.get('password', '')}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()
    else:
        raise ValueError(f"unknown auth type: {auth.get('type')!r}")


def _build_headers(headers: Optional[Mapping[str, Any]], json_body: Any,
                   auth: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    result = {str(key): str(value) for key, value in (headers or {}).items()}
    has_content_type = any(key.lower() == "content-type" for key in result)
    if json_body is not None and not has_content_type:
        result["Content-Type"] = "application/json"
    _apply_auth(result, auth)
    return result


def _encode_body(json_body: Any, data: Any) -> Optional[bytes]:
    if json_body is not None:
        return json.dumps(json_body).encode("utf-8")
    if data is None:
        return None
    return data.encode("utf-8") if isinstance(data, str) else bytes(data)


def _try_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _read_response(response: Any) -> Dict[str, Any]:
    status = int(getattr(response, "status", None) or getattr(response, "code", 0))
    text = response.read().decode("utf-8", errors="replace")
    raw_headers = getattr(response, "headers", None)
    headers = dict(raw_headers.items()) if raw_headers else {}
    return {
        "status": status,
        "ok": 200 <= status < 400,
        "headers": headers,
        "text": text,
        "json": _try_json(text),
        "url": getattr(response, "url", None),
    }


def http_request(url: str, method: str = "GET",
                 headers: Optional[Mapping[str, Any]] = None,
                 json_body: Any = None, data: Any = None,
                 auth: Optional[Mapping[str, Any]] = None,
                 timeout: float = _DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Perform an HTTP(S) request and return a response dict.

    ``json_body`` is serialised to JSON (setting Content-Type when absent);
    ``data`` sends a raw string/bytes body. ``auth`` is a dict such as
    ``{"type": "bearer", "token": ...}`` or
    ``{"type": "basic", "username": ..., "password": ...}``. Non-2xx/3xx
    responses are returned (with their body) rather than raised, so callers
    can assert on status codes.
    """
    _validate_url(url)
    from je_auto_control.utils.egress.egress_policy import get_egress_policy
    get_egress_policy().check(url)  # allow-all unless an operator locked it down
    request = urllib.request.Request(
        url, data=_encode_body(json_body, data), method=str(method).upper(),
        headers=_build_headers(headers, json_body, auth))
    try:
        with urllib.request.urlopen(  # nosec B310 — scheme allow-listed
                request, timeout=float(timeout)) as response:
            return _read_response(response)
    except urllib.error.HTTPError as error:
        return _read_response(error)
