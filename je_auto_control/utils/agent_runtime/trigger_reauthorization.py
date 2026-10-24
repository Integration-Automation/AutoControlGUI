"""Explicitly replace a trigger's unavailable origins while retaining its event history and template."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.policy import TaskPolicy
from je_auto_control.utils.agent_runtime.recovery_authorization import (
    prepare_authorization, authorized_template, narrowed_template, authorization_details,
)
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.agent_runtime.trigger_config import validate_config
from je_auto_control.utils.agent_runtime.trigger_history import seed_history, snapshot_events
from je_auto_control.utils.agent_runtime.trigger_registration import insert_registration
from je_auto_control.utils.rbac.authorization import AuthorizationContext
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

OPERATIONS = ("review_authorization", "create_authorized")


def authorization_metadata(connection: Any, identifier: str) -> dict:
    """Expose only an authorized binding's lineage proof and durable replacement identity."""
    result = {}
    row = connection.execute("SELECT details,source_trigger FROM agent_trigger_authorizations WHERE trigger_id=?",
                             (identifier,)).fetchone()
    if row is not None:
        result["reauthorization"] = {**json.loads(row["details"]), "source_trigger": row["source_trigger"]}
    row = connection.execute("SELECT trigger_id FROM agent_trigger_authorizations WHERE source_trigger=?",
                             (identifier,)).fetchone()
    if row is not None:
        result["replacement"] = row["trigger_id"]
    return result


def _snapshot(connection: Any, source: dict) -> tuple[str, int]:
    live = connection.execute("SELECT * FROM agent_triggers WHERE id=?", (source["id"],)).fetchone()
    if live is None:
        raise AgentTaskError("trigger snapshot changed; review authorization again")
    digest, count = snapshot_events(connection, source["id"])
    return request_spec_digest({"source": dict(live), "events": digest}), count


# pylint: disable-next=too-few-public-methods  # reason: one fixed review/create protocol on the existing trigger service
class TriggerReauthorization:
    """Retire the original binding atomically with one explicitly approved future-event registration."""

    def __init__(self, triggers: Any) -> None:
        self.triggers = triggers

    def control(self, operation: str, request: dict) -> dict:
        """Require current owner/operator review; old tasks and native input ownership are never resumed."""
        fields = {"trigger_id"}
        if operation == "create_authorized":
            fields |= {"snapshot", "authorization_review", "spec", "note"}
        if set(request) != fields or not isinstance(request["trigger_id"], str):
            raise AgentTaskError("invalid trigger authorization fields")
        runtime = self.triggers.runtime
        # pylint: disable-next=protected-access  # reason: serialize with firing, removal and enable/disable operations
        with runtime._lock("trigger:" + request["trigger_id"]), DeferredAuthorization.capture().scope():
            # pylint: disable-next=protected-access  # reason: reuse the trigger's existing owner-scoped lookup
            source = self.triggers._row(request["trigger_id"])
            if operation == "review_authorization":
                return self._review(source)
            return self._create(source, request)

    def _review(self, source: dict) -> dict:
        runtime = self.triggers.runtime
        with runtime.store.connection() as connection:
            metadata = authorization_metadata(connection, source["id"])
            snapshot, count = _snapshot(connection, source)
        if "replacement" in metadata:
            return {"trigger_id": source["id"], "existing_registration": metadata["replacement"],
                    "spec": None, "issues": ["already_reauthorized"], "approval_required": False}
        authorization = prepare_authorization(AgentTaskSpec.from_dict(source["spec"]), snapshot)
        template = self._template(source, authorization)
        reviewed: dict | None = None
        issues = []
        try:
            # pylint: disable-next=protected-access  # reason: renewal cannot advertise a template outside current scope
            spec = runtime._validated_spec(template)
            validate_config(source["kind"], source["config"], TaskPolicy(spec))
            reviewed = spec.to_dict()
        except AgentTaskError:
            issues = ["authorization_scope_unavailable"]
        return {"trigger_id": source["id"], "snapshot": snapshot, "event_count": count,
                "authorization_review": authorization["review"], "authorization": authorization["context"],
                "spec": reviewed, "kind": source["kind"], "config": source["config"],
                "name": source["name"], "max_pending": source["max_pending"], "issues": issues,
                "approval_required": True, "activation": "future_events"}

    @staticmethod
    def _template(source: dict, authorization: dict) -> dict:
        template = authorized_template(source["spec"], authorization)
        template["actions"] = source["spec"]["actions"]
        return template

    def _create(self, source: dict, request: dict) -> dict:
        runtime = self.triggers.runtime
        note = request["note"]
        if not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise AgentTaskError("trigger authorization requires a bounded nonempty review note")
        authorization = prepare_authorization(AgentTaskSpec.from_dict(source["spec"]), request["snapshot"])
        if request["authorization_review"] != authorization["review"]:
            raise AgentTaskError("trigger authorization context changed; review authorization again")
        # pylint: disable-next=protected-access  # reason: creation repeats current host and policy validation
        spec = runtime._validated_spec(request["spec"])
        expected = narrowed_template(self._template(source, authorization), spec.to_dict())
        if request_spec_digest(expected) != request_spec_digest(spec.to_dict()):
            raise AgentTaskError("trigger authorization must preserve its full template and completion criteria")
        config = validate_config(source["kind"], source["config"], TaskPolicy(spec))
        details = {**authorization_details(authorization, spec), "note": note}
        owner = AuthorizationContext(**source["owner"]) if source["owner"] else None
        with DeferredAuthorization(owner).scope():
            return self._insert(source, request, spec, config, details)

    def _insert(self, source: dict, request: dict, spec: AgentTaskSpec, config: dict, details: dict) -> dict:
        with self.triggers.runtime.store.connection(write=True) as connection:
            previous = connection.execute("SELECT * FROM agent_trigger_authorizations WHERE source_trigger=?",
                                          (source["id"],)).fetchone()
            spec_hash = request_spec_digest(spec.to_dict())
            if previous is not None:
                return self._existing(connection, previous, request, spec_hash)
            if _snapshot(connection, source)[0] != request["snapshot"]:
                raise AgentTaskError("trigger snapshot changed; review authorization again")
            identifier, now = uuid.uuid4().hex, time.time()
            insert_registration(connection, identifier, source, spec, config, source["owner"], now)
            family = seed_history(connection, source["id"])
            connection.execute("INSERT INTO agent_trigger_authorizations VALUES (?,?,?,?,?,?,?,?)",
                (source["id"], identifier, family, request["snapshot"], spec_hash,
                 json.dumps(details), now, 1))
            connection.execute("UPDATE agent_triggers SET enabled=0 WHERE id=?", (source["id"],))
        return {"trigger_id": identifier, "source_trigger": source["id"], "enabled": True,
                "kind": source["kind"], "reauthorization": details}

    @staticmethod
    def _existing(connection: Any, previous: Any, request: dict, spec_hash: str) -> dict:
        details = json.loads(previous["details"])
        if (previous["snapshot"] != request["snapshot"] or previous["spec_hash"] != spec_hash
                or details["review"] != request["authorization_review"]):
            raise AgentTaskError("trigger already has a different reviewed replacement")
        live = connection.execute("SELECT enabled,kind FROM agent_triggers WHERE id=?",
                                  (previous["trigger_id"],)).fetchone()
        return {"trigger_id": previous["trigger_id"], "source_trigger": previous["source_trigger"],
                "enabled": bool(live["enabled"]) if live is not None else False,
                "retired": live is None, "reauthorization": details}
