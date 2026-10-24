"""Public service-backed task functions; imports never start services or operate targets."""
from __future__ import annotations

import json
import os
import subprocess  # nosec B404  # reason: explicit owned runtime process with a fixed argv list
import sys
import time
from concurrent.futures import CancelledError
from pathlib import Path
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.policy import canonical_spec
from je_auto_control.utils.agent_runtime.service import default_connection_path
from je_auto_control.utils.rbac.authorization import AuthorizationError, current_authorization
from je_auto_control.utils.rbac.users import Capability
from je_auto_control.utils.exception.cancellation import cancellation_scope
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


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


def submit_agent_task(spec: AgentTaskSpec | Mapping[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
    """Validate and submit a task to the explicitly running local service."""
    validated = spec if isinstance(spec, AgentTaskSpec) else AgentTaskSpec.from_dict(spec)
    validated = canonical_spec(validated)
    payload: dict[str, Any] = {"spec": validated.to_dict()}
    if idempotency_key is not None:
        payload["idempotency_key"] = idempotency_key
    return AgentRuntimeClient().call("submit", payload)


def lookup_agent_task(idempotency_key: str) -> dict[str, Any]:
    """Inspect an accepted request by its original owner's key, without submission or resume."""
    return AgentRuntimeClient().call("lookup", {"idempotency_key": idempotency_key})


def inspect_agent_dag(definition: Mapping[str, Any], timeout_seconds: float = 30) -> dict[str, Any]:
    """Inspect local/registered-host task keys without submitting, resuming or granting continuation."""
    from je_auto_control.utils.dag.inspection import inspect_definition
    return inspect_definition(definition, timeout_seconds)


def get_agent_task(task_id: str) -> dict[str, Any]:
    """Read one owner-scoped task snapshot."""
    return AgentRuntimeClient().call("get", {"task_id": task_id})


def list_agent_tasks() -> dict[str, Any]:
    """List task snapshots visible to the current caller."""
    return AgentRuntimeClient().call("list")


def get_agent_task_receipts(task_id: str, offset: int = 0, limit: int = 100) -> dict[str, Any]:
    """Read paged owner-scoped action receipts, review witnesses and workflow row outcomes."""
    return AgentRuntimeClient().call("receipts", {"task_id": task_id, "offset": offset, "limit": limit})


def reconcile_agent_task(task_id: str, review: Mapping[str, Any]) -> dict[str, Any]:
    """Record a human-reviewed uncertain outcome; this neither resumes a task nor forces success."""
    return AgentRuntimeClient().call("reconcile", {"task_id": task_id, "review": dict(review)})


def prune_agent_tasks(keep_days: int = 30) -> dict[str, Any]:
    """Prune expired visible metadata and owned artifacts, preserving user files and external journals."""
    return AgentRuntimeClient().call("prune", {"keep_days": keep_days})


def manage_agent_trigger(operation: str, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Register, inspect, pause or fire a durable, preauthorized task trigger."""
    return AgentRuntimeClient().call("trigger", {"operation": operation, "request": dict(request or {})})


def list_agent_triggers() -> dict[str, Any]:
    """List durable trigger metadata visible to this caller without firing or observing a target."""
    return manage_agent_trigger("list")


def recover_agent_target(target: str, note: str) -> dict[str, Any]:
    """Review host-crash input ownership after manually releasing held keys/buttons."""
    return AgentRuntimeClient().call("recover_target", {"target": target, "note": note})


def manage_agent_skill(operation: str, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Record, parameterize, validate, explicitly publish or run an immutable managed skill version."""
    return AgentRuntimeClient().call("skill", {"operation": operation, "request": dict(request or {})})


def list_agent_skills() -> dict[str, Any]:
    """List owner-visible immutable skill candidates and published versions."""
    return manage_agent_skill("list")


def manage_agent_target(operation: str, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Register an immutable host-reviewed target or explicitly change its availability."""
    return AgentRuntimeClient().call("target", {"operation": operation, "request": dict(request or {})})


def list_agent_targets() -> dict[str, Any]:
    """Read passive target names and declared support without connecting or exposing host configuration."""
    return AgentRuntimeClient().call("targets")


def observe_agent_task(task_id: str) -> dict[str, Any]:
    """Acquire the authorized target and obtain a fresh, versioned observation."""
    return _task_call("observe", task_id)


def act_agent_task(task_id: str, action: Mapping[str, Any]) -> dict[str, Any]:
    """Apply one grounded action through the host's current task policy."""
    return _task_call("act", task_id, {"action": dict(action)})


def finish_agent_task(task_id: str) -> dict[str, Any]:
    """Request deterministic completion verification; never force a success status."""
    return _task_call("finish", task_id)


def _task_call(operation: str, task_id: str, extra: dict | None = None) -> dict[str, Any]:
    client = AgentRuntimeClient()
    try:
        return client.call(operation, {"task_id": task_id, **(extra or {})})
    except (CancelledError, KeyboardInterrupt):
        try:
            with cancellation_scope(None):
                client.call("pause", {"task_id": task_id}, timeout=3)
        except (AutoControlException, OSError, RuntimeError, ValueError, TypeError, LookupError) as error:
            autocontrol_logger.warning("host pause after cancellation is unconfirmed: %s", type(error).__name__)
        raise


def pause_agent_task(task_id: str) -> dict[str, Any]:
    """Pause input and release control after owned work retires."""
    return AgentRuntimeClient().call("pause", {"task_id": task_id})


def resume_agent_task(task_id: str) -> dict[str, Any]:
    """Reauthorize and queue a task that can safely resume."""
    return AgentRuntimeClient().call("resume", {"task_id": task_id})


def cancel_agent_task(task_id: str) -> dict[str, Any]:
    """Cancel future operations and retire owned input."""
    return AgentRuntimeClient().call("cancel", {"task_id": task_id})


def stop_all_agent_tasks() -> dict[str, Any]:
    """Emergency-stop all tasks visible to this caller, retaining uncertain receipts for review."""
    return AgentRuntimeClient().call("stop_all", {})


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
