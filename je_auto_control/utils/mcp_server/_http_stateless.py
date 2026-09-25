"""The Streamable HTTP rules of MCP 2026-07-28, for the dual-era HTTP transport.

A stateless request mirrors parts of its body into headers so that gateways
can route and meter it without parsing JSON: ``MCP-Protocol-Version`` (the
``_meta`` version), ``Mcp-Method``, and for ``tools/call``, ``prompts/get``
and ``resources/read`` also ``Mcp-Name`` (the tool or prompt name, or the
resource URI). The server must refuse a request whose headers are missing or
disagree with the body, since a gateway may have routed it on the headers
while the server acts on the body: 400 with ``HeaderMismatch``. A bad version
or missing metadata is also 400, an unknown method 404, and no session is
kept for any of it.

Pure functions: they read the headers and the parsed body and say what to
answer. :mod:`.http_transport` does the answering.
"""
import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from je_auto_control.utils.mcp_server._protocol import _error_response, _MCPError
from je_auto_control.utils.mcp_server._stateless import (
    DISCOVER_METHOD, HEADER_MISMATCH, META_PROTOCOL_VERSION,
    MISSING_REQUIRED_CLIENT_CAPABILITY, STATELESS_METHODS, STATELESS_PROTOCOL_VERSIONS,
    UNSUPPORTED_PROTOCOL_VERSION, all_supported_versions, stateless_request,
)

PROTOCOL_VERSION_HEADER = "MCP-Protocol-Version"
METHOD_HEADER = "Mcp-Method"
NAME_HEADER = "Mcp-Name"
#: Where ``Mcp-Name`` comes from, per method that needs it.
_NAME_SOURCE = {"tools/call": "name", "prompts/get": "name", "resources/read": "uri"}
_SENTINEL_PREFIX = "=?base64?"
_SENTINEL_SUFFIX = "?="
#: Errors a modern client recognises as a modern server's; all are 400 on HTTP.
_BAD_REQUEST_CODES = frozenset({
    HEADER_MISMATCH, MISSING_REQUIRED_CLIENT_CAPABILITY, UNSUPPORTED_PROTOCOL_VERSION,
})


class Headers(Protocol):
    """What is read of the request headers: ``http.server``'s message, or a dict."""

    def get(self, name: str) -> Optional[str]:
        """The header's value, ``None`` when absent."""


@dataclass(frozen=True)
class Refusal:
    """An HTTP status and the JSON-RPC error response line to answer with."""

    status: int
    body: str


def read_message(line: str) -> Optional[Dict[str, Any]]:
    """The request body as a JSON object, or ``None`` when it is not one."""
    try:
        message = json.loads(line)
    except (ValueError, RecursionError):
        return None
    return message if isinstance(message, dict) else None


def _meta_version(message: Dict[str, Any]) -> Any:
    """The body's ``_meta`` protocol version; ``None`` when the key is absent."""
    params = message.get("params")
    meta = params.get("_meta") if isinstance(params, dict) else None
    if not isinstance(meta, dict):
        return None
    return meta.get(META_PROTOCOL_VERSION)


def is_stateless(headers: Headers, message: Optional[Dict[str, Any]]) -> bool:
    """True when the header or the body declares a 2026-07-28 request."""
    if (headers.get(PROTOCOL_VERSION_HEADER) or "").strip() in STATELESS_PROTOCOL_VERSIONS:
        return True
    return message is not None and _meta_version(message) is not None


def unsupported_header_refusal(headers: Headers,
                               message: Optional[Dict[str, Any]]) -> Optional[Refusal]:
    """400 with ``UnsupportedProtocolVersion`` when the header names a version not served."""
    version = headers.get(PROTOCOL_VERSION_HEADER)
    if version is None or version.strip() in all_supported_versions():
        return None
    msg_id = message.get("id") if message is not None else None
    return Refusal(400, _error_response(
        msg_id, UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version",
        {"supported": list(all_supported_versions()), "requested": version}))


def decode_header_value(value: str) -> Optional[str]:
    """A header value as the body holds it; ``None`` when it is not a valid one.

    Plain values are visible ASCII, space and tab. Anything else travels as
    ``=?base64?<UTF-8, Base64>?=``, which is decoded here.
    """
    if value.startswith(_SENTINEL_PREFIX) and value.endswith(_SENTINEL_SUFFIX) \
            and len(value) >= len(_SENTINEL_PREFIX) + len(_SENTINEL_SUFFIX):
        encoded = value[len(_SENTINEL_PREFIX):len(value) - len(_SENTINEL_SUFFIX)]
        try:
            return base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
    if all(char == "\t" or " " <= char <= "~" for char in value):
        return value
    return None


def _mismatch(msg_id: Any, detail: str) -> Refusal:
    return Refusal(400, _error_response(msg_id, HEADER_MISMATCH, f"Header mismatch: {detail}"))


def _header_refusal(headers: Headers, msg_id: Any, method: str,
                    params: Dict[str, Any]) -> Optional[Refusal]:
    """``HeaderMismatch`` when ``Mcp-Method`` or ``Mcp-Name`` is missing or disagrees."""
    header_method = headers.get(METHOD_HEADER)
    if header_method is None:
        return _mismatch(msg_id, f"{METHOD_HEADER} header is required")
    if header_method != method:
        return _mismatch(msg_id, f"{METHOD_HEADER} {header_method!r} does not match body {method!r}")
    source = _NAME_SOURCE.get(method)
    body_name = params.get(source) if source is not None else None
    if not isinstance(body_name, str):
        # No name to mirror, or one the dispatcher refuses as invalid params.
        return None
    header_name = headers.get(NAME_HEADER)
    if header_name is None:
        return _mismatch(msg_id, f"{NAME_HEADER} header is required for {method}")
    if decode_header_value(header_name) != body_name:
        return _mismatch(msg_id, f"{NAME_HEADER} does not match body {source}")
    return None


def stateless_refusal(headers: Headers,
                      message: Optional[Dict[str, Any]]) -> Optional[Refusal]:
    """How to refuse a 2026-07-28 POST before dispatch; ``None`` to serve it.

    Only requests are checked: a body that is not a JSON-RPC request is left
    to the dispatcher, which answers it the usual way.
    """
    if message is None or message.get("id") is None or not isinstance(message.get("method"), str):
        return None
    msg_id, method = message["id"], message["method"]
    params = message.get("params")
    if not isinstance(params, dict):
        return None
    refused = (_version_refusal(headers, msg_id, message, params)
               or _header_refusal(headers, msg_id, method, params))
    if refused is not None:
        return refused
    if method != DISCOVER_METHOD and method not in STATELESS_METHODS:
        return Refusal(404, _error_response(msg_id, -32601, f"Method not found: {method}"))
    return None


def _version_refusal(headers: Headers, msg_id: Any, message: Dict[str, Any],
                     params: Dict[str, Any]) -> Optional[Refusal]:
    """The header and ``_meta`` must name the same served version, with valid metadata."""
    header_version = headers.get(PROTOCOL_VERSION_HEADER)
    body_version = _meta_version(message)
    if header_version is None:
        return _mismatch(msg_id, f"{PROTOCOL_VERSION_HEADER} header is required")
    if body_version is None:
        return Refusal(400, _error_response(
            msg_id, -32602, f"Invalid params: _meta must carry {META_PROTOCOL_VERSION}"))
    if header_version.strip() != body_version:
        return _mismatch(msg_id, f"{PROTOCOL_VERSION_HEADER} does not match body _meta")
    try:
        stateless_request(params)
    except _MCPError as error:
        return Refusal(400, _error_response(msg_id, error.code, error.message, error.data))
    return None


def status_for(response: str) -> int:
    """The HTTP status of a dispatched 2026-07-28 reply."""
    reply = read_message(response)
    error = reply.get("error") if reply is not None else None
    code = error.get("code") if isinstance(error, dict) else None
    if code == -32601:
        return 404
    return 400 if code in _BAD_REQUEST_CODES else 200
