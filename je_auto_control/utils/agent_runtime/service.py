"""Explicit local runtime service lifecycle over the existing authenticated REST server."""
from __future__ import annotations

import json
import secrets
import threading
from contextvars import Context
from pathlib import Path
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


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
        self.runtime.source_private_files = (*self.runtime.source_private_files, self._connection)
        self._generation = secrets.token_hex(16)
        self._maintenance: threading.Thread | None = None
        self._triggers: threading.Thread | None = None
        from je_auto_control.utils.agent_runtime.jobs import BackgroundTasks
        self._jobs = BackgroundTasks(self.runtime)
        self.runtime.background = self._jobs
        # pylint: disable-next=import-outside-toplevel  # reason: bind service workers after runtime construction
        from je_auto_control.utils.agent_runtime.dag_jobs import BackgroundDags
        self._dag_jobs = BackgroundDags(self.runtime)
        self.runtime.background_dags = self._dag_jobs

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
        self.runtime.transfers.enable()
        self._dag_jobs.enable()
        self._jobs.start_pending()
        self._maintenance = threading.Thread(target=lambda: Context().run(self._maintain),
                                             name="AgentLeaseWatch", daemon=True)
        self._maintenance.start()
        self._triggers = threading.Thread(target=lambda: Context().run(self._poll_triggers),
                                          name="AgentTriggerWatch", daemon=True)
        self._triggers.start()
        return self.status()

    def _maintain(self) -> None:
        while not self._stop.wait(0.25):
            try:
                self.runtime.maintain()
            except (AutoControlException, OSError, RuntimeError, ValueError, TypeError) as error:
                autocontrol_logger.warning("agent lease maintenance needs review: %s", type(error).__name__)

    def _poll_triggers(self) -> None:
        while not self._stop.wait(1):
            try:
                self.runtime.triggers.poll()
            except (AutoControlException, OSError, RuntimeError, ValueError, TypeError) as error:
                autocontrol_logger.warning("agent trigger polling needs review: %s", type(error).__name__)

    def status(self) -> dict[str, Any]:
        """Return inert service metadata; credentials never appear in status or logs."""
        return {"running": self._server is not None, "connection_path": str(self._connection),
                "generation": self._generation}

    def wait(self) -> None:
        """Keep an explicitly launched service alive until it receives a stop request."""
        self.runtime.shutdown_requested.wait()

    def close(self) -> None:
        """Retire owned task input, listener and matching connection metadata."""
        self._stop.set()
        for worker in (self._maintenance, self._triggers):
            if worker is None:
                continue
            worker.join(timeout=3)
            if worker.is_alive():
                raise AgentTaskError("agent lease maintenance has not retired")
        self._dag_jobs.close()
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
