"""Audit log for MCP tool calls.

With a sink configured, every ``tools/call`` produces one JSONL line with
timestamp, tool name, sanitised arguments, status (``ok`` / ``error`` /
``cancelled`` / ``denied``), and duration.

**The log is off by default.** The sink is the ``path`` given to
:class:`AuditLogger`, else the file ``JE_AUTOCONTROL_MCP_AUDIT`` names; with
neither -- or with the variable empty -- nothing is recorded and no file is
created anywhere, the working directory included. (This docstring used to
promise a default ``mcp_audit.jsonl`` in the working directory. No version
wrote one, and a server must not start leaving a file of tool arguments
wherever it happens to be launched from; a deployment that needs the trail
sets the variable, with no code change.)

When the call was made by an authenticated RBAC user the line also carries
``user_id`` and ``role``; a call refused for its role is recorded with
status ``denied``.
"""
import json
import os
import threading
import time
from typing import Any, Dict, Optional

from je_auto_control.utils.executor.action_redaction import SENSITIVE_ARGUMENT_NAMES, redact_actions
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.rbac.authorization import current_authorization


class AuditLogger:
    """Thread-safe JSONL audit logger for MCP tool calls; a no-op without a sink.

    ``path`` is the file to append to. ``None`` reads
    ``JE_AUTOCONTROL_MCP_AUDIT``; if that is unset or empty the logger is
    disabled (:attr:`enabled` is ``False``) and :meth:`record` does nothing.
    """

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
        """The file entries are appended to; ``None`` when the log is off."""
        return self._path

    @property
    def enabled(self) -> bool:
        """Whether a sink is configured, i.e. whether :meth:`record` writes."""
        return self._path is not None

    def record(self, *, tool: str, arguments: Dict[str, Any],
               status: str, duration_seconds: float,
               error_text: Optional[str] = None,
               artifact_path: Optional[str] = None,
               user_id: Optional[str] = None) -> None:
        """Append one audit entry. No-ops when no path is configured.

        ``user_id`` defaults to the RBAC user the calling thread is serving,
        so the entry names who made the call without each call site passing
        it along; with no such user the entry has no ``user_id`` at all.
        """
        if self._path is None:
            return
        caller = current_authorization()
        if user_id is None and caller is not None:
            user_id = caller.user_id
        entry = {
            "ts": time.time(),
            "tool": tool,
            "arguments": _sanitise(arguments),
            "status": status,
            "duration_seconds": float(duration_seconds),
        }
        if user_id is not None:
            entry["user_id"] = user_id
            if caller is not None and caller.user_id == user_id:
                entry["role"] = caller.role
        if error_text is not None:
            entry["error"] = error_text
        if artifact_path is not None:
            entry["artifact_path"] = artifact_path
        line = json.dumps(entry, ensure_ascii=False, default=str)
        try:
            with self._lock:
                with open(self._path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except OSError as error:
            # Recorded after the tool ran: raising here turned a click that
            # happened into an internal error, inviting a retry, and put the
            # log's absolute path in the reply.
            autocontrol_logger.warning("MCP audit log not written (%s): %r", tool, error)


REDACTED_KEYS = SENSITIVE_ARGUMENT_NAMES
REDACTED_PLACEHOLDER = "<redacted>"


def _sanitise(arguments: Any) -> Any:
    """Replace secret-like values with ``REDACTED_PLACEHOLDER``, at any depth.

    Only top-level names were checked, so a passphrase inside an ``actions``
    list (``ac_execute_actions``) or under a name missing from the list
    (``key``, ``passphrase``) was written to the audit file as is. Action
    lists are masked with the executor's own rules.
    """
    if isinstance(arguments, list):
        return [_sanitise(item) for item in redact_actions(arguments)]
    if not isinstance(arguments, dict):
        return arguments
    out: Dict[str, Any] = {}
    for key, value in arguments.items():
        if str(key).lower() in REDACTED_KEYS or str(key).lower() == "key":
            out[key] = REDACTED_PLACEHOLDER
        else:
            out[key] = _sanitise(value)
    return out


__all__ = ["AuditLogger", "REDACTED_KEYS", "REDACTED_PLACEHOLDER"]
