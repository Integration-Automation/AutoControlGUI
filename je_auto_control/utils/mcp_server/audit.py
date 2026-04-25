"""Audit log for MCP tool calls.

Every ``tools/call`` produces one JSONL line with timestamp, tool
name, sanitised arguments, status (``ok`` / ``error``), and
duration. The default sink is ``$JE_AUTOCONTROL_MCP_AUDIT`` (or
``mcp_audit.jsonl`` next to the cwd) so deployments that need a
forensic trail get it without code changes.
"""
import json
import os
import threading
import time
from typing import Any, Dict, Optional


class AuditLogger:
    """Thread-safe JSONL audit logger for MCP tool calls."""

    def __init__(self, path: Optional[str] = None) -> None:
        resolved = path
        if resolved is None:
            resolved = os.environ.get("JE_AUTOCONTROL_MCP_AUDIT")
        self._path: Optional[str] = (
            os.path.realpath(os.fspath(resolved)) if resolved else None
        )
        self._lock = threading.Lock()

    @property
    def path(self) -> Optional[str]:
        return self._path

    @property
    def enabled(self) -> bool:
        return self._path is not None

    def record(self, *, tool: str, arguments: Dict[str, Any],
               status: str, duration_seconds: float,
               error_text: Optional[str] = None) -> None:
        """Append one audit entry. No-ops when no path is configured."""
        if self._path is None:
            return
        entry = {
            "ts": time.time(),
            "tool": tool,
            "arguments": _sanitise(arguments),
            "status": status,
            "duration_seconds": float(duration_seconds),
        }
        if error_text is not None:
            entry["error"] = error_text
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")


_REDACTED_KEYS = frozenset({"password", "token", "secret", "api_key",
                            "authorization"})


def _sanitise(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Replace obvious secret-like values with ``"<redacted>"``."""
    if not isinstance(arguments, dict):
        return arguments
    out: Dict[str, Any] = {}
    for key, value in arguments.items():
        if key.lower() in _REDACTED_KEYS:
            out[key] = "<redacted>"
        else:
            out[key] = value
    return out


__all__ = ["AuditLogger"]
