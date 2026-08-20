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
from typing import Any, Dict, List, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.tools import MCPContent
from je_auto_control.utils.sqlite_support import SQLITE_ERRORS


PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "je_auto_control"
SERVER_VERSION = "0.1.0"
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
_BUILTIN_DISPATCH_ERRORS = (
    OSError, RuntimeError, ValueError, TypeError, KeyError,
)
_DISPATCH_ERRORS = _BUILTIN_DISPATCH_ERRORS + _FRAMEWORK_TOOL_ERRORS
_TOOL_INVOKE_ERRORS = (
    _BUILTIN_DISPATCH_ERRORS + (AttributeError,) + _FRAMEWORK_TOOL_ERRORS
)


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


def _notification_message(method: str, params: Dict[str, Any]) -> str:
    return json.dumps({"jsonrpc": "2.0", "method": method, "params": params},
                      ensure_ascii=False, default=str)


def _result_response(msg_id: Any, result: Any) -> str:
    return json.dumps(
        {"jsonrpc": "2.0", "id": msg_id, "result": result},
        ensure_ascii=False, default=str,
    )


def _error_response(msg_id: Any, code: int, message: str) -> str:
    return json.dumps({
        "jsonrpc": "2.0", "id": msg_id,
        "error": {"code": code, "message": message},
    }, ensure_ascii=False)
