"""JSON-RPC 2.0 wire format for the MCP server.

Everything here is about the protocol rather than the server: the version
and identity constants, the error classes and the error tuples that decide
what a failing tool is allowed to do, the envelope builders, and the pure
functions that normalise a tool's return value into MCP ``content`` blocks.

None of it touches server state, so it is importable and testable without
starting a server.
"""
import json
import os
import subprocess  # nosec B404  # reason: only its TimeoutExpired type is referenced
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Type

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.http_headers import wire_json_text
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.tools import MCPContent
from je_auto_control.utils.sqlite_support import SQLITE_ERRORS


PROTOCOL_VERSION = "2025-11-25"
#: Every revision this server speaks, newest first. ``initialize`` answers with
#: the client's version when it is one of these, else with the newest.
#: 2025-11-25's server-side changes are optional features this server does not
#: offer (icons, tasks, URL elicitation, sampling with tools) plus rules it
#: follows for every version: input validation errors are tool execution
#: errors, tool names use ``[A-Za-z0-9_.-]``, and input schemas read as
#: JSON Schema 2020-12. 2026-07-28 (stateless, ``server/discover``) is not
#: spoken: see Progress.md.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


def negotiate_protocol_version(requested: Any) -> str:
    """The version to answer ``initialize`` with (MCP lifecycle, version negotiation).

    A version the server does not implement is never echoed back: the client
    would take it as agreed and use features this server does not have.
    """
    return requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
SERVER_NAME = "je_auto_control"
SERVER_VERSION = "0.1.0"
#: ``Implementation.description``, sent to clients that negotiated 2025-11-25 or later.
SERVER_DESCRIPTION = ("Cross-platform GUI automation: mouse and keyboard control, image, OCR "
                      "and accessibility-tree location, and action scripts.")
#: The first revision whose ``Implementation`` carries ``description``.
_DESCRIPTION_SINCE = "2025-11-25"
_TOOLS_CALL_METHOD = "tools/call"

# Framework and external-library errors a tool handler may raise. They all
# subclass ``Exception`` directly (not OSError/RuntimeError/…), so without
# listing them here a failing tool would escape both containment layers — the
# stdio worker thread dies and the client waits forever, or the HTTP
# connection aborts with no JSON-RPC reply. ``AutoControlException`` is the
# family base every ``AutoControl*Exception``/``ImageNotFoundException`` now
# derives from.
_FRAMEWORK_TOOL_ERRORS = (
    AutoControlException, subprocess.TimeoutExpired, *SQLITE_ERRORS,
)
# ArithmeticError / LookupError: an OverflowError from ``1e400`` or an
# IndexError from a short list killed the stdio worker, and that request
# never got a reply.
_BUILTIN_DISPATCH_ERRORS = (
    OSError, RuntimeError, ValueError, TypeError, ArithmeticError, LookupError,
)
_DISPATCH_ERRORS: Tuple[Type[BaseException], ...] = (
    _BUILTIN_DISPATCH_ERRORS + _FRAMEWORK_TOOL_ERRORS
)
_TOOL_INVOKE_ERRORS: Tuple[Type[BaseException], ...] = (
    _BUILTIN_DISPATCH_ERRORS + (AttributeError,) + _FRAMEWORK_TOOL_ERRORS
)


class _InvalidToolArguments(Exception):
    """A ``tools/call`` whose arguments fail the tool's input schema.

    Answered as a tool execution error (``isError: true``), not a JSON-RPC
    error: the model can read it and retry with corrected arguments (MCP
    2025-11-25, SEP-1303; 2025-06-18 already listed invalid input there).
    """


def _server_info(protocol_version: str) -> Dict[str, Any]:
    """The ``serverInfo`` for ``initialize``, as the negotiated revision defines it."""
    info: Dict[str, Any] = {"name": SERVER_NAME, "version": SERVER_VERSION}
    if protocol_version >= _DESCRIPTION_SINCE:
        info["description"] = SERVER_DESCRIPTION
    return info


class _MCPError(Exception):
    """Raised inside the dispatcher to surface a JSON-RPC error response."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _to_content_blocks(result: Any) -> List[Dict[str, Any]]:
    """Normalise a tool's return value into MCP ``content`` blocks."""
    if isinstance(result, MCPContent):
        return [result.to_dict()]
    if isinstance(result, list) and result and \
            all(isinstance(item, MCPContent) for item in result):
        return [item.to_dict() for item in result]
    return [{"type": "text", "text": _stringify_result(result)}]


def _stringify_result(value: Any) -> str:
    """Convert a tool return value into a model-readable string."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(value)


def _confirm_destructive_enabled() -> bool:
    """Return True when the operator wants destructive tools gated on user OK."""
    raw = os.environ.get("JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _capture_error_screenshot(tool_name: str) -> Optional[str]:
    """Save a debug screenshot when JE_AUTOCONTROL_MCP_ERROR_SHOTS is set."""
    debug_dir = os.environ.get("JE_AUTOCONTROL_MCP_ERROR_SHOTS")
    if not debug_dir:
        return None
    target_dir = os.path.realpath(os.fspath(debug_dir))
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as error:
        autocontrol_logger.info(
            "MCP error-screenshot dir unavailable: %r", error,
        )
        return None
    filename = f"{tool_name}_{int(time.time() * 1000)}.png"
    path = os.path.join(target_dir, filename)
    try:
        from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
        pil_screenshot(file_path=path)
    except (OSError, RuntimeError, ValueError, AttributeError,
            ImportError) as error:
        autocontrol_logger.info(
            "MCP failed to capture error screenshot: %r", error,
        )
        return None
    return path


def _file_uri_to_path(uri: str) -> Optional[str]:
    """Convert a ``file://`` URI to a local filesystem path; ``None`` otherwise."""
    if not isinstance(uri, str) or not uri.startswith("file://"):
        return None
    from urllib.parse import unquote, urlparse
    parsed = urlparse(uri)
    # file://server/share/x named another host; dropping the host read the
    # local /share/x instead.
    if parsed.netloc not in ("", "localhost"):
        return None
    raw_path = unquote(parsed.path)
    # Windows: file:///C:/foo strips the leading slash before the drive letter.
    if sys.platform.startswith("win") and raw_path.startswith("/") and \
            len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    return raw_path or None


def _is_hashable(value: Any) -> bool:
    """Return True when ``value`` can be used as a dict key."""
    try:
        hash(value)
    except TypeError:
        return False
    return True


def _coerce_params(raw: Any, msg_id: Any) -> tuple:
    """Normalise JSON-RPC ``params`` to a dict.

    Returns ``(params, error_line)``. Every handler here expects an object;
    a non-object ``params`` yields a ``-32602`` error line for a request and
    an empty dict for a notification (which cannot carry an error reply).
    """
    if raw is None:
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    if msg_id is None:
        return {}, None
    return {}, _error_response(msg_id, -32602, "Invalid params: expected an object")


# wire_json_text: a lone surrogate (a tool listing an undecodable file name)
# could not be written as UTF-8, and the reply never reached the client.
def _notification_message(method: str, params: Dict[str, Any]) -> str:
    return wire_json_text({"jsonrpc": "2.0", "method": method, "params": params},
                          default=str)


def _result_response(msg_id: Any, result: Any) -> str:
    return wire_json_text({"jsonrpc": "2.0", "id": msg_id, "result": result},
                          default=str)


def _error_response(msg_id: Any, code: int, message: str) -> str:
    return wire_json_text({
        "jsonrpc": "2.0", "id": msg_id,
        "error": {"code": code, "message": message},
    })
