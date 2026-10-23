"""Public service-backed task functions; imports never start services or operate targets."""
from __future__ import annotations

import json
import os
import subprocess  # nosec B404  # reason: explicit owned runtime process with a fixed argv list
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.service import default_connection_path
from je_auto_control.utils.rbac.authorization import AuthorizationError, current_authorization
from je_auto_control.utils.rbac.users import Capability


def start_agent_runtime(directory: str | None = None) -> dict[str, Any]:
    """Explicitly start a hidden, independent local service, or attach to the current one."""
    identity = current_authorization()
    if identity is not None and not identity.allows(Capability.MANAGE_HOSTS):
        raise AuthorizationError("starting the agent runtime requires manage_hosts")
    path = Path(directory).resolve() if directory else default_connection_path().parent
    connection = path / "agent_runtime.json"
    if _available(connection):
        return {"running": True, "connection_path": str(connection)}
    path.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "-m", "je_auto_control.utils.agent_runtime", "serve", "--directory", str(path)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    process = subprocess.Popen(  # nosec B603  # reason: fixed owned runtime module with explicit argv, no shell
                               argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=flags,
                               start_new_session=os.name != "nt")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _available(connection):
            return {"running": True, "connection_path": str(connection)}
        if process.poll() is not None:
            raise AgentTaskError("agent runtime startup failed; inspect the configured log")
        time.sleep(0.05)
    process.terminate()
    process.wait(timeout=5)
    raise AgentTaskError("agent runtime startup timed out")


def _available(connection: Path) -> bool:
    if not connection.is_file():
        return False
    try:
        AgentRuntimeClient(connection).call("list")
        return True
    except AgentTaskError:
        return False


def submit_agent_task(spec: AgentTaskSpec | Mapping[str, Any]) -> dict[str, Any]:
    """Validate and submit a task to the explicitly running local service."""
    validated = spec if isinstance(spec, AgentTaskSpec) else AgentTaskSpec.from_dict(spec)
    return AgentRuntimeClient().call("submit", {"spec": validated.to_dict()})


def get_agent_task(task_id: str) -> dict[str, Any]:
    """Read one owner-scoped task snapshot."""
    return AgentRuntimeClient().call("get", {"task_id": task_id})


def list_agent_tasks() -> dict[str, Any]:
    """List task snapshots visible to the current caller."""
    return AgentRuntimeClient().call("list")


def observe_agent_task(task_id: str) -> dict[str, Any]:
    """Acquire the authorized target and obtain a fresh, versioned observation."""
    return AgentRuntimeClient().call("observe", {"task_id": task_id})


def act_agent_task(task_id: str, action: Mapping[str, Any]) -> dict[str, Any]:
    """Apply one grounded action through the host's current task policy."""
    return AgentRuntimeClient().call("act", {"task_id": task_id, "action": dict(action)})


def finish_agent_task(task_id: str) -> dict[str, Any]:
    """Request deterministic completion verification; never force a success status."""
    return AgentRuntimeClient().call("finish", {"task_id": task_id})


def pause_agent_task(task_id: str) -> dict[str, Any]:
    """Pause input and release control after owned work retires."""
    return AgentRuntimeClient().call("pause", {"task_id": task_id})


def resume_agent_task(task_id: str) -> dict[str, Any]:
    """Reauthorize and queue a task that can safely resume."""
    return AgentRuntimeClient().call("resume", {"task_id": task_id})


def cancel_agent_task(task_id: str) -> dict[str, Any]:
    """Cancel future operations and retire owned input."""
    return AgentRuntimeClient().call("cancel", {"task_id": task_id})


def agent_runtime_status() -> dict[str, Any]:
    """Return inert local connection metadata without reading or returning credentials."""
    path = default_connection_path()
    if not path.is_file():
        return {"configured": False, "connection_path": str(path)}
    metadata = json.loads(path.read_text(encoding="utf-8"))
    return {"configured": True, "connection_path": str(path), "generation": metadata.get("generation")}


def stop_agent_runtime() -> dict[str, Any]:
    """Request service cancellation and retirement; an active input owner prevents shutdown."""
    return AgentRuntimeClient().call("shutdown", {})
