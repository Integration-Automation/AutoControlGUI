"""Shared local service client for GUI, CLI, MCP and Python task operations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.service import default_connection_path
from je_auto_control.utils.agent_runtime.transport import request_json


class AgentRuntimeClient:
    """Read the current local service identity for every request, never caching bearer credentials."""

    def __init__(self, connection_path: str | Path | None = None) -> None:
        self._path = Path(connection_path) if connection_path is not None else default_connection_path()

    def call(self, operation: str, body: dict[str, Any] | None = None, *, timeout: float = 30) -> dict[str, Any]:
        """Perform a known local task operation without accepting arbitrary URLs or methods."""
        allowed = {"list", "get", "submit", "observe", "act", "finish", "pause", "resume", "cancel",
                   "shutdown", "draft", "stop_all", "receipts", "reconcile", "prune", "trigger", "recover_target",
                   "skill", "target", "targets", "lookup", "recovery", "dag"}
        if operation not in allowed:
            raise AgentTaskError("unknown task operation")
        try:
            metadata = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise AgentTaskError("agent runtime is not running; start it explicitly") from error
        parsed = urlparse(metadata.get("url", ""))
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path:
            raise AgentTaskError("invalid local runtime connection metadata")
        url = metadata["url"]
        if operation in {"list", "targets", "get"}:
            path = {"list": "/agent/tasks", "targets": "/agent/targets", "get": "/agent/task"}[operation]
            if operation == "get":
                path += "?" + urlencode(body or {})
            return request_json(url + path, token=metadata["token"], timeout=timeout, delegate_local=True)
        return request_json(url + f"/agent/{operation}", body={} if body is None else body,
                            token=metadata["token"], timeout=timeout,
                            control=operation in {"pause", "cancel", "shutdown", "stop_all"}, delegate_local=True)
