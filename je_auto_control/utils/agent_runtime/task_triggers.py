"""Durable preauthorized task bindings with owner refresh, bounded backlog and event deduplication."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from time import monotonic
from pathlib import Path
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.policy import TaskPolicy, durable_payload, owns_task
from je_auto_control.utils.agent_runtime.trigger_config import validate_config, next_due
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.exception.exceptions import AutoControlException

OPERATIONS = ("register", "list", "get", "enable", "disable", "fire", "remove")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _decode(row: Any) -> dict[str, Any]:
    data = dict(row)
    for name in ("spec", "owner", "config"):
        data[name] = json.loads(data[name])
    return data


class AgentTriggers:
    """A runtime-owned registry; no watcher or schedule starts when the module is imported."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self._stable: dict[str, tuple[str, float]] = {}

    def _row(self, trigger_id: str) -> dict[str, Any]:
        with self.runtime.store.connection() as connection:
            row = connection.execute("SELECT * FROM agent_triggers WHERE id=?", (trigger_id,)).fetchone()
        identity = current_authorization()
        if row is None:
            raise AgentTaskError("trigger does not exist or belongs to another caller")
        data = _decode(row)
        if not owns_task(data["owner"], identity):
            raise AgentTaskError("trigger does not exist or belongs to another caller")
        return data

    def register(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Capture the authorized immutable task template and schedule before enabling future fires."""
        value = detached(request)
        _register_fields(value)
        spec = self.runtime._validated_spec(value["spec"])
        config = validate_config(value["kind"], value.get("config", {}), TaskPolicy(spec))
        identifier, now = uuid.uuid4().hex, time.time()
        with DeferredAuthorization.capture().context_scope() as owner:
            with DeferredAuthorization(owner).scope():
                metadata = {"user_id": owner.user_id, "role": owner.role,
                            "store_path": owner.store_path} if owner else {}
                self._insert(identifier, value, spec, config, metadata, now)
        return {"trigger_id": identifier, "enabled": True, "kind": value["kind"]}

    def _insert(self, identifier: str, value: dict, spec: AgentTaskSpec, config: dict, owner: dict, now: float) -> None:
        with self.runtime.store.connection(write=True) as connection:
            if connection.execute("SELECT COUNT(*) FROM agent_triggers").fetchone()[0] >= 200:
                raise AgentTaskError("a runtime supports at most two hundred configured task triggers")
            connection.execute("INSERT INTO agent_triggers VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (identifier, value.get("name", spec.goal), value["kind"], json.dumps(durable_payload(spec.to_dict())),
                 json.dumps(owner), json.dumps(config), 1, next_due(value["kind"], config, now), "",
                 value.get("max_pending", 1), "", now))

    def list(self) -> dict[str, Any]:
        """List visible binding metadata without exposing another owner's task template."""
        with self.runtime.store.connection() as connection:
            identifiers = [row[0] for row in connection.execute(
                "SELECT id FROM agent_triggers ORDER BY created LIMIT 200")]
        identity = current_authorization()
        rows = []
        for identifier in identifiers:
            with self.runtime.store.connection() as connection:
                raw = connection.execute("SELECT * FROM agent_triggers WHERE id=?", (identifier,)).fetchone()
            if raw is None:
                continue
            row = _decode(raw)
            if owns_task(row["owner"], identity):
                rows.append({key: row[key] for key in ("id", "name", "kind", "enabled", "next_run", "error")})
        return {"triggers": rows}

    def control(self, operation: str, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch a fixed registry operation; caller data never names an arbitrary method."""
        value = detached({} if request is None else request)
        if not isinstance(operation, str) or operation not in OPERATIONS or not isinstance(value, dict):
            raise AgentTaskError("trigger requests must be objects")
        if operation == "register":
            return self.register(value)
        if operation == "list":
            if value:
                raise AgentTaskError("trigger list accepts an empty request")
            return self.list()
        return self._control_existing(operation, value)

    def _control_existing(self, operation: str, value: dict) -> dict:
        _existing_fields(operation, value)
        row = self._row(value["trigger_id"])
        if operation == "fire":
            return self.fire(row, value["event_key"], value.get("payload", {}))
        if operation == "get":
            return {"trigger": {key: item for key, item in row.items() if key != "owner"}}
        with self.runtime._lock("trigger:" + row["id"]):
            row = self._row(row["id"])
            if operation in {"enable", "disable"}:
                return self._enabled(row, operation == "enable")
            if operation == "remove":
                return self._remove(row)
        raise AgentTaskError("unknown trigger operation")

    def _enabled(self, row: dict, enabled: bool) -> dict:
        owner = AuthorizationContext(**row["owner"]) if row["owner"] else None
        if enabled:
            with DeferredAuthorization(owner).scope():
                return self._set_enabled(row, True)
        return self._set_enabled(row, False)

    def _set_enabled(self, row: dict, enabled: bool) -> dict:
        with self.runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE agent_triggers SET enabled=?,error='',next_run=? WHERE id=?",
                               (int(enabled), next_due(row["kind"], row["config"], time.time()), row["id"]))
        return {"trigger_id": row["id"], "enabled": enabled}

    def _remove(self, row: dict) -> dict:
        with self.runtime.store.connection(write=True) as connection:
            connection.execute("DELETE FROM agent_trigger_events WHERE trigger_id=?", (row["id"],))
            connection.execute("DELETE FROM agent_triggers WHERE id=?", (row["id"],))
        self._stable.pop(row["id"], None)
        return {"trigger_id": row["id"], "removed": True}

    def fire(self, row: dict, event_key: str, payload: Any = None) -> dict[str, Any]:
        """Deduplicate an event and queue a fresh task within its preauthorized template only."""
        if not row["enabled"] or not isinstance(event_key, str) or not event_key or len(event_key) > 256:
            raise AgentTaskError("trigger is disabled or event_key is invalid")
        payload = durable_payload({} if payload is None else payload)
        if len(json.dumps(payload).encode("utf-8")) > 65536:
            raise AgentTaskError("trigger event payload exceeds sixty-four kilobytes")
        digest = _digest(event_key)
        owner = AuthorizationContext(**row["owner"]) if row["owner"] else None
        with DeferredAuthorization(owner).scope():
            with self.runtime._lock("trigger:" + row["id"]):
                return self._fire_owned(row, digest, payload)

    def _fire_owned(self, row: dict, digest: str, payload: Any) -> dict:
        with self.runtime.store.connection() as connection:
            live = connection.execute("SELECT enabled FROM agent_triggers WHERE id=?", (row["id"],)).fetchone()
            if live is None or not live["enabled"]:
                return {"deferred": True, "reason": "trigger is disabled or removed"}
            previous = connection.execute("SELECT * FROM agent_trigger_events WHERE trigger_id=? AND event_hash=?",
                                          (row["id"], digest)).fetchone()
            pending = connection.execute("SELECT COUNT(*) FROM agent_trigger_events e "
                "JOIN agent_tasks t ON t.id=e.task_id "
                "WHERE e.trigger_id=? AND t.state NOT IN ('succeeded','failed','cancelled','timed_out')",
                (row["id"],)).fetchone()[0]
        if previous is not None:
            if previous["payload_hash"] != _digest(payload):
                raise AgentTaskError("event_key was already used with a different payload")
            result = self._event_result(previous["task_id"], duplicate=True)
            if result["state"] == "queued" and self.runtime.background is not None:
                self.runtime.background.start(previous["task_id"])
            return result
        if pending >= row["max_pending"]:
            return {"deferred": True, "reason": "trigger pending-task limit reached"}
        return self._queue(row, digest, payload)

    def _queue(self, row: dict, digest: str, payload: Any) -> dict:
        spec = detached(row["spec"])
        spec["inputs"] = {**spec.get("inputs", {}), "event": {"key": digest, "payload": payload}}
        spec["options"] = {**spec.get("options", {}), "trigger": {"id": row["id"], "event": digest}}
        validated = self.runtime._validated_spec(spec)
        task = self.runtime._create_task(validated, "trigger:" + row["id"] + ":" + digest,
                                         (row["id"], digest, _digest(payload)))
        if self.runtime.background is not None:
            self.runtime.background.start(task.task_id)
        return self._event_result(task.task_id, duplicate=False)

    def _event_result(self, task_id: str, *, duplicate: bool) -> dict:
        with self.runtime.store.connection() as connection:
            row = connection.execute("SELECT state FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        return {"task_id": task_id, "duplicate": duplicate, "state": row[0] if row else "expired"}

    def poll(self) -> None:
        """Check bounded schedules/file versions, reauthorizing each registrant before every fire."""
        with self.runtime.store.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_triggers WHERE enabled=1 ORDER BY created LIMIT 200").fetchall()
        for raw in rows:
            row = _decode(raw)
            owner = AuthorizationContext(**row["owner"]) if row["owner"] else None
            try:
                with DeferredAuthorization(owner).scope():
                    self._poll_one(row)
            except AuthorizationError:
                self._fault(row["id"], "trigger owner authorization was revoked")
            except (AutoControlException, OSError, ValueError, TypeError) as error:
                self._fault(row["id"], f"trigger needs review: {type(error).__name__}")

    def _poll_one(self, row: dict) -> None:
        if row["kind"] == "event":
            return
        if row["kind"] == "file":
            self._poll_file(row)
            return
        now = time.time()
        if now < row["next_run"]:
            return
        result = self.fire(row, str(row["next_run"]), {"scheduled": row["next_run"]})
        if not result.get("deferred"):
            with self.runtime.store.connection(write=True) as connection:
                connection.execute("UPDATE agent_triggers SET next_run=? WHERE id=?",
                                   (next_due(row["kind"], row["config"], now), row["id"]))

    def _poll_file(self, row: dict) -> None:
        spec = AgentTaskSpec.from_dict(row["spec"])
        path = Path(TaskPolicy(spec).path(row["config"]["path"]))
        if not path.is_file():
            return
        info = path.stat()
        digest = _digest([str(path), info.st_size, info.st_mtime_ns, info.st_ino])
        if digest == row["last_event"]:
            return
        previous = self._stable.setdefault(row["id"], (digest, monotonic()))
        if previous[0] != digest:
            self._stable[row["id"]] = digest, monotonic()
            return
        if monotonic() - previous[1] < row["config"]["stable_seconds"]:
            return
        result = self.fire(row, digest, {"path": str(path), "bytes": info.st_size})
        if not result.get("deferred"):
            with self.runtime.store.connection(write=True) as connection:
                connection.execute("UPDATE agent_triggers SET last_event=? WHERE id=?", (digest, row["id"]))

    def _fault(self, trigger_id: str, reason: str) -> None:
        with self.runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE agent_triggers SET enabled=0,error=? WHERE id=?", (reason, trigger_id))


def _register_fields(value: Any) -> None:
    if not isinstance(value, dict) or not {"kind", "spec"} <= set(value):
        raise AgentTaskError("trigger registration requires kind and spec")
    if set(value) - {"kind", "spec", "config", "name", "max_pending"}:
        raise AgentTaskError("unknown trigger registration fields")
    pending = value.get("max_pending", 1)
    if isinstance(pending, bool) or not isinstance(pending, int) or not 1 <= pending <= 100:
        raise AgentTaskError("trigger max_pending must be between one and one hundred")
    if "name" in value and (not isinstance(value["name"], str) or not 1 <= len(value["name"]) <= 200):
        raise AgentTaskError("trigger name must be nonempty text of at most two hundred characters")


def _existing_fields(operation: str, value: dict) -> None:
    required = {"trigger_id", "event_key"} if operation == "fire" else {"trigger_id"}
    optional = {"payload"} if operation == "fire" else set()
    if not required <= set(value) or set(value) - required - optional:
        raise AgentTaskError("invalid trigger operation fields")
