"""Explicit local runtime service lifecycle over the existing authenticated REST server."""
from __future__ import annotations

import json
import secrets
import threading
from pathlib import Path
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.runtime import AgentRuntime


def default_connection_path() -> Path:
    """Resolve the per-user connection file at use time, including isolated test homes."""
    return Path.home() / ".je_auto_control" / "agent_runtime.json"


class AgentRuntimeService:
    """Own a single runtime and REST listener; construction performs no native operation."""

    def __init__(self, directory: str | Path, *, targets: Mapping[str, Any] | None = None) -> None:
        self.directory = Path(directory).resolve()
        self.runtime = AgentRuntime(self.directory / "agent_runtime.sqlite", targets=targets)
        self._server: Any = None
        self._stop = threading.Event()
        self._connection = self.directory / "agent_runtime.json"
        self._generation = secrets.token_hex(16)
        from je_auto_control.utils.agent_runtime.jobs import BackgroundTasks
        self._jobs = BackgroundTasks(self.runtime)
        self.runtime.background = self._jobs

    def start(self) -> dict[str, Any]:
        """Bind loopback on an ephemeral port; publish credentials only in the local owner file."""
        from je_auto_control.utils.json_store.json_store import atomic_write_text
        from je_auto_control.utils.rest_api.rest_server import RestApiServer
        if self._server is not None:
            return self.status()
        token = secrets.token_urlsafe(48)
        server = RestApiServer(port=0, token=token, enable_audit=True, agent_runtime=self.runtime,
                               use_environment_users=False)
        try:
            server.start()
            metadata = {"url": server.base_url, "token": token, "generation": self._generation}
            atomic_write_text(self._connection, json.dumps(metadata))
            self._connection.chmod(0o600)
        except BaseException:  # reason: a partial start owns and must close its listener before propagating
            server.stop()
            self.runtime.close()
            raise
        self._server = server
        self._jobs.start_pending()
        return self.status()

    def status(self) -> dict[str, Any]:
        """Return inert service metadata; credentials never appear in status or logs."""
        return {"running": self._server is not None, "connection_path": str(self._connection),
                "generation": self._generation}

    def wait(self) -> None:
        """Keep an explicitly launched service alive until it receives a stop request."""
        self.runtime.shutdown_requested.wait()

    def close(self) -> None:
        """Retire owned task input, listener and matching connection metadata."""
        self._jobs.close()
        self.runtime.close()
        if self._server is not None:
            self._server.stop()
            self._server = None
        if self._connection.is_file():
            metadata = json.loads(self._connection.read_text(encoding="utf-8"))
            if metadata.get("generation") == self._generation:
                self._connection.unlink()
        self._stop.set()
