"""Shared local service client for GUI, CLI, MCP and Python task operations."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.service import default_connection_path
from je_auto_control.utils.agent_runtime.transport import request_json
from je_auto_control.utils.agent_runtime.control_admission import control_request


def _connection_identity(metadata: dict[str, Any]) -> str:
    generation = metadata.get("generation")
    if not isinstance(generation, str) or not 1 <= len(generation) <= 128:
        raise AgentTaskError("bound runtime operations require a valid service generation")
    payload = json.dumps([metadata["url"], metadata["token"], generation], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_local_metadata(value: Any) -> dict[str, Any]:
    if (not isinstance(value, dict) or not isinstance(value.get("url"), str)
            or not isinstance(value.get("token"), str) or not value["token"]):
        raise AgentTaskError("invalid local runtime connection metadata")
    try:
        parsed = urlparse(value["url"])
        valid = all((parsed.scheme == "http", parsed.hostname == "127.0.0.1", not parsed.path,
                     parsed.username is None, parsed.password is None, not parsed.query, not parsed.fragment,
                     parsed.port != 0))
    except ValueError:
        raise AgentTaskError("invalid local runtime connection metadata") from None
    if not valid:
        raise AgentTaskError("invalid local runtime connection metadata")
    return value


class AgentRuntimeClient:
    """Read the current local service identity for every request, never caching bearer credentials."""

    def __init__(self, connection_path: str | Path | None = None) -> None:
        self._path = Path(connection_path) if connection_path is not None else default_connection_path()
        self._identity: str | None = None

    def bound(self) -> AgentRuntimeClient:
        """Pin one local service path/identity without retaining its bearer credential."""
        metadata = self._metadata()
        client = AgentRuntimeClient(self._path.resolve())
        # pylint: disable-next=protected-access  # reason: clone only the identity hash, never the bearer credential
        client._identity = _connection_identity(metadata)
        client.check_binding()
        return client

    def check_binding(self) -> None:
        """Re-read the local owner file and reject replaced credentials, endpoint or generation."""
        self._metadata()

    def task_call(self, operation: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Use this same client for local node transport instead of discovering another service."""
        return self.call(operation, body, timeout=timeout)

    def _metadata(self) -> dict[str, Any]:
        try:
            metadata = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise AgentTaskError("agent runtime is not running; start it explicitly") from error
        metadata = _validate_local_metadata(metadata)
        if self._identity is not None and _connection_identity(metadata) != self._identity:
            raise AgentTaskError("local runtime connection changed; explicit batch review is required")
        return metadata

    def call(self, operation: str, body: dict[str, Any] | None = None, *, timeout: float = 30) -> dict[str, Any]:
        """Perform a known local task operation without accepting arbitrary URLs or methods."""
        allowed = {"list", "get", "submit", "observe", "act", "finish", "pause", "resume", "cancel",
                   "shutdown", "draft", "stop_all", "receipts", "reconcile", "prune", "trigger", "recover_target",
                   "skill", "target", "targets", "lookup", "recovery", "dag"}
        if operation not in allowed:
            raise AgentTaskError("unknown task operation")
        metadata = self._metadata()
        url = metadata["url"]
        if operation in {"list", "targets", "get"}:
            path = {"list": "/agent/tasks", "targets": "/agent/targets", "get": "/agent/task"}[operation]
            if operation == "get":
                path += "?" + urlencode(body or {})
            return request_json(url + path, token=metadata["token"], timeout=timeout, delegate_local=True)
        payload = {} if body is None else body
        return request_json(url + f"/agent/{operation}", body=payload,
                            token=metadata["token"], timeout=timeout,
                            control=control_request(f'/agent/{operation}', payload), delegate_local=True)
