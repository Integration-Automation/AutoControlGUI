"""Perform HTTP(S) requests headlessly for first-class API action steps.

A small, dependency-free client built on the standard library, so the
package needs no ``requests`` dependency. Supports method, headers, a JSON
or raw body, basic/bearer auth, and an explicit timeout; it returns a
plain response dict (status / ok / headers / text / json / url) so that
non-2xx responses are inspectable rather than raised. Imports no
``PySide6`` and only allows http/https schemes (Bandit B310).
"""
import base64
import http.client
import json
import urllib.error
import urllib.parse
import urllib.request

from je_auto_control.utils.http_headers import CREDENTIAL_HEADERS
from typing import Any, Dict, Mapping, Optional

# NOSONAR python:S5332 — http is allow-listed deliberately (other schemes
# are rejected); plain http is required for internal/localhost endpoints.
_ALLOWED_SCHEMES = ("http://", "https://")  # NOSONAR python:S5332
_DEFAULT_TIMEOUT = 30.0
# The whole body is held in memory (and decoded, and parsed as JSON), so an
# endless or huge response used to exhaust memory.
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


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
    if isinstance(data, int):
        # bytes(5) is five NUL bytes, not "5".
        raise TypeError("data must be str or bytes, not int")
    return data.encode("utf-8") if isinstance(data, str) else bytes(data)


def _try_json(text: str) -> Any:
    try:
        return json.loads(text)
    # RecursionError: a reply nested thousands deep raised it out of every
    # http_request -- a server's body could crash the caller.
    except (ValueError, TypeError, RecursionError):
        return None


def _read_response(response: Any) -> Dict[str, Any]:
    raw_status: Any = getattr(response, "status", None)
    if raw_status is None:
        raw_status = getattr(response, "code", 0)
    status = int(raw_status)
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise urllib.error.URLError(
            f"response body exceeds {MAX_RESPONSE_BYTES} bytes")
    text = body.decode("utf-8", errors="replace")
    raw_headers = getattr(response, "headers", None)
    headers, set_cookie = _collect_headers(raw_headers)
    return {
        "status": status,
        "ok": 200 <= status < 400,
        "headers": headers,
        "set_cookie": set_cookie,
        "text": text,
        "json": _try_json(text),
        "url": getattr(response, "url", None),
    }


def _collect_headers(raw_headers: Any) -> "tuple[Dict[str, str], list]":
    """Response headers with repeats joined, plus every ``Set-Cookie`` value.

    ``dict(headers.items())`` kept only the last of a repeated header, so a
    second ``Link`` or ``Set-Cookie`` silently replaced the first. Repeats
    are joined with ", " (RFC 9110 5.3) except ``Set-Cookie``, whose dates
    contain commas: it keeps its last value under ``headers`` and all of
    them in the list.
    """
    headers: Dict[str, str] = {}
    set_cookie: list = []
    for name, value in (raw_headers.items() if raw_headers else []):
        if name.lower() == "set-cookie":
            set_cookie.append(value)
            headers[name] = value
        elif name in headers:
            headers[name] = f"{headers[name]}, {value}"
        else:
            headers[name] = value
    return headers, set_cookie


def build_call(url: str, method: str = "GET",
               headers: Optional[Mapping[str, Any]] = None,
               json_body: Any = None, data: Any = None,
               auth: Optional[Mapping[str, Any]] = None,
               timeout: float = _DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Build a transport ``call`` dict (url/method/headers/body/timeout)."""
    _validate_url(url)
    return {
        "url": url, "method": str(method).upper(),
        "headers": _build_headers(headers, json_body, auth),
        "body": _encode_body(json_body, data), "timeout": float(timeout),
    }


class _CheckedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Apply the scheme allow-list and the egress policy to every redirect.

    Only the first URL used to be checked, so a server on an allowed host
    could redirect to any other host -- or to ``ftp://``.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        from je_auto_control.utils.egress.egress_policy import get_egress_policy
        _validate_url(newurl)
        get_egress_policy().check(newurl)
        new_request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_request is not None and _origin(newurl) != _origin(req.full_url):
            # urllib carries every header over, so a redirect to another host
            # received the Authorization meant for this one -- and a redirect
            # from https to http on the same host sent it in the clear.
            for name in CREDENTIAL_HEADERS:
                # Request stores header names capitalize()d.
                new_request.remove_header(name.capitalize())
        return new_request


class _RefusingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Return a 3xx as the response instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def _origin(url: str) -> "tuple[str, str]":
    parts = urllib.parse.urlsplit(url)
    return parts.scheme.lower(), (parts.netloc or "").lower()


_OPENER = urllib.request.build_opener(_CheckedRedirectHandler)
_NO_REDIRECT_OPENER = urllib.request.build_opener(_RefusingRedirectHandler)


def urllib_transport(call: Mapping[str, Any]) -> Dict[str, Any]:
    """The default live transport: perform a ``call`` with ``urllib``.

    A malformed reply (``http.client.HTTPException``: a garbage status
    line, a truncated body) is raised as ``urllib.error.URLError``, the
    ``OSError`` every other transport failure already arrives as. With
    ``call["follow_redirects"]`` false a 3xx comes back as the response.
    """
    request = urllib.request.Request(
        call["url"], data=call.get("body"), method=call["method"],
        headers=dict(call.get("headers") or {}))
    opener = _OPENER if call.get("follow_redirects", True) else _NO_REDIRECT_OPENER
    try:
        with opener.open(  # nosec B310 — scheme allow-listed, redirects too
                request, timeout=float(call.get("timeout", _DEFAULT_TIMEOUT))) \
                as response:
            return _read_response(response)
    except urllib.error.HTTPError as error:
        return _read_error_response(error)
    except http.client.HTTPException as error:
        raise urllib.error.URLError(f"malformed HTTP response: {error!r}") from error


def _read_error_response(error: urllib.error.HTTPError) -> Dict[str, Any]:
    """A 4xx / 5xx response, read and closed like any other.

    Read inside the ``except HTTPError`` clause, a truncated error body raised
    ``http.client.IncompleteRead`` past the clause below it -- no OSError, so
    it aborted the script -- and the response was never closed.
    """
    try:
        with error:
            return _read_response(error)
    except http.client.HTTPException as bad:
        raise urllib.error.URLError(f"malformed HTTP response: {bad!r}") from bad


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
    return perform_call(build_call(url, method, headers, json_body, data, auth, timeout))


def perform_call(call: Mapping[str, Any]) -> Dict[str, Any]:
    """Send a :func:`build_call` dict after the egress-policy check.

    The one path every outbound request in the package should take, so the
    egress policy, the redirect checks and the malformed-reply handling apply
    to all of them. Set ``call["follow_redirects"] = False`` to get a 3xx back
    instead of following it.
    """
    from je_auto_control.utils.egress.egress_policy import get_egress_policy
    get_egress_policy().check(call["url"])  # allow-all unless an operator locked it down
    return urllib_transport(call)
