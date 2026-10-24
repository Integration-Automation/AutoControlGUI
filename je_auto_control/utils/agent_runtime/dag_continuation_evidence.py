"""Bounded read-only destination evidence for explicit whole-batch continuation decisions."""
from __future__ import annotations

import time
from typing import Any, cast

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import positive
from je_auto_control.utils.agent_runtime.submission import submitted_digest
from je_auto_control.utils.dag import managed_tasks
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.exception.exceptions import AutoControlException


class ContinuationEvidence:
    """Use captured matching host endpoints, bounded deadlines and no submit/resume/control operation."""

    def __init__(self, batch: dict, timeout: float = 30, runtime: Any = None) -> None:
        positive(timeout, "DAG continuation timeout_seconds", 300)
        self.batch = batch
        self.deadline = time.monotonic() + timeout
        self.owner = DeferredAuthorization.capture()
        self.calls: dict[str, Any] = {}
        self.runtime = runtime

    def query(self, node: dict, operation: str, body: dict) -> dict:
        """Refresh authority around one pinned lookup/get, hiding transport diagnostics."""
        host = node["host"]
        managed_tasks.authorize_task_host(self.owner, host)
        if managed_tasks.task_stop_requested():
            raise AgentTaskError("DAG continuation review was stopped")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTaskError("DAG continuation review deadline exhausted")
        try:
            reply = self._read(host, operation, body, min(5, remaining))
        except AuthorizationError:
            raise
        except (AutoControlException, OSError, RuntimeError, ValueError, TypeError, LookupError):
            raise AgentTaskError("DAG continuation destination evidence is unavailable") from None
        managed_tasks.authorize_task_host(self.owner, host)
        if time.monotonic() >= self.deadline:
            raise AgentTaskError("DAG continuation review deadline exhausted")
        if not isinstance(reply, dict):
            raise AgentTaskError("DAG continuation destination evidence is malformed")
        return reply

    def _read(self, host: str, operation: str, body: dict, timeout: float) -> dict:
        if host == "local" and self.runtime is not None:
            return self._local(operation, body)
        if host not in self.calls:
            self.calls[host] = managed_tasks.bound_task_connection(host, self.batch["hosts"][host])
        return self.calls[host](operation, body, timeout)

    def _local(self, operation: str, body: dict) -> dict:
        with self.owner.scope():
            if operation == "lookup":
                return self.runtime.lookup(body["idempotency_key"], body.get("spec"))
            if operation == "get":
                return self.runtime.get(body["task_id"]).to_dict()
        raise AgentTaskError("continuation evidence accepts read-only lookup/get only")

    def original(self, node: dict) -> dict | None:
        """Identify the accepted original spec through a submission witness or live legacy matching."""
        key = {"idempotency_key": node["task"]["idempotency_key"]}
        reply = self.query(node, "lookup", key)
        if reply.get("found") is False and reply.get("task") is None:
            return None
        task = reply.get("task")
        if reply.get("found") is not True or not isinstance(task, dict):
            raise AgentTaskError("DAG continuation original request identity is unverified")
        metadata = task.get("metadata", {})
        version = metadata.get("submission_contract") if isinstance(metadata, dict) else None
        # pylint: disable-next=unidiomatic-typecheck  # reason: exact protocol integer excludes boolean versions
        if type(version) is int and version == 1:
            if metadata.get("submitted_spec_digest") != submitted_digest(node["task"]["spec"]):
                raise AgentTaskError("DAG continuation original submitted specification differs")
        else:
            matched = self.query(node, "lookup", {**key, "spec": node["task"]["spec"]})
            _legacy_match(matched, task)
            task = matched["task"]
        return task

    def successor(self, node: dict, original: dict, identifier: str) -> tuple[dict, list[dict]]:
        """Follow only real runtime recovery provenance; every candidate must independently complete."""
        candidate = self.query(node, "get", {"task_id": identifier})
        if candidate.get("task_id") != identifier:
            raise AgentTaskError("DAG continuation successor identity changed")
        completion(candidate, node)
        current, seen = candidate, set()
        chain: list[dict] = []
        for _index in range(16):
            current_id = current.get("task_id")
            if not isinstance(current_id, str) or current_id in seen:
                break
            seen.add(current_id)
            metadata = current.get("metadata")
            recovery = metadata.get("recovery") if isinstance(metadata, dict) else None
            source = recovery.get("source_task") if isinstance(recovery, dict) else None
            chain.append(cast(dict, semantic_task(current)))
            if source == original.get("task_id"):
                return candidate, chain
            if not isinstance(source, str):
                break
            current = self.query(node, "get", {"task_id": source})
            if current.get("task_id") != source:
                break
        raise AgentTaskError("DAG continuation successor has no verified source recovery chain")


def _legacy_match(reply: dict, initial: dict) -> None:
    version = reply.get("spec_match_contract")
    # pylint: disable-next=unidiomatic-typecheck  # reason: exact legacy protocol integer excludes bool
    if type(version) is not int or version != 1 or reply.get("spec_match") != "matches":
        raise AgentTaskError("DAG continuation legacy request binding is unverified")
    task = reply.get("task")
    if reply.get("found") is not True or not isinstance(task, dict) or task.get("task_id") != initial.get("task_id"):
        raise AgentTaskError("DAG continuation original request identity changed")


def completion(task: dict, node: dict) -> None:
    """Share strict independent clauses and input retirement without interpreting historical screen state."""
    managed_tasks.validate_recorded_completion(task, node["task"]["spec"])


def semantic_task(task: dict | None) -> dict | None:
    """Bind stable evidence only, excluding elapsed time, private paths and raw diagnostics."""
    if task is None:
        return None
    metadata = task.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    fields = ("input_released", "completion_contract", "submission_contract", "submitted_spec_digest", "recovery")
    return {"task_id": task.get("task_id"), "state": task.get("state"), "verification": task.get("verification"),
            "metadata": {key: metadata[key] for key in fields if key in metadata}}
