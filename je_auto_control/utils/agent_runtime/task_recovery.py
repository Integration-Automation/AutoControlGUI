"""Review stopped finite workflows and create one explicitly approved successor without replay."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError, AgentHumanReview
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.policy import durable_payload
from je_auto_control.utils.agent_runtime.receipts import effective_actions, row_report
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.agent_runtime.workflow_values import verified_prefix, transformed
from je_auto_control.utils.rbac.authorization import current_authorization, AuthorizationError
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.users import Capability

OPERATIONS = ("preview", "create")
_STOPPED = frozenset({"paused", "waiting_user", "recovering", "cancelled", "timed_out", "failed"})
_POINTER_TOOLS = ("AC_click_mouse", "AC_set_mouse_position", "AC_mouse_scroll", "AC_press_mouse", "AC_release_mouse",
                  "AC_android_tap", "AC_android_swipe")


def recovery_link(store: Any, task_id: str) -> dict:
    """Return durable successor provenance, without treating the source as completed."""
    with store.connection() as connection:
        row = connection.execute("SELECT source_task,snapshot,note,created FROM agent_task_recoveries "
                                 "WHERE task_id=?", (task_id,)).fetchone()
    return dict(row) if row is not None else {}


def require_no_successor(store: Any, task_id: str) -> None:
    """Keep a delegated source stopped, even after its successor's task metadata expires."""
    with store.connection() as connection:
        linked = connection.execute("SELECT 1 FROM agent_task_recoveries WHERE source_task=?", (task_id,)).fetchone()
    if linked is not None:
        raise AgentHumanReview("task already has a reviewed successor; continue from that task")


# pylint: disable-next=too-few-public-methods  # reason: one closed operation entry point is the recovery protocol
class AgentRecovery:
    """Keep source receipts intact and bind explicit approval to a stopped task snapshot."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def control(self, operation: str, request: Any = None) -> dict:
        """Preview without target access, or create an owner-scoped, deduplicated successor."""
        request = durable_payload(detached(request))
        required = {"task_id"} if operation == "preview" else {"task_id", "snapshot", "spec", "note"}
        if operation not in OPERATIONS or not isinstance(request, dict) or set(request) != required:
            raise AgentTaskError("invalid recovery operation fields")
        task_id = request["task_id"]
        if not isinstance(task_id, str) or not task_id:
            raise AgentTaskError("recovery requires a task_id")
        # pylint: disable-next=protected-access  # reason: trusted lifecycle collaborator uses the runtime's task lock
        with self.runtime._lock(task_id), DeferredAuthorization.capture().scope():
            _require_operator()
            # pylint: disable-next=protected-access  # reason: reuse the runtime's owner and closed-state check
            row = self.runtime._row(task_id)
            if operation == "create":
                return self._create(row, request)
            receipts, reviews = self._read(row)
            return self._preview(row, receipts, reviews)

    def _read(self, row: dict) -> tuple[list[dict], list[dict]]:
        # pylint: disable-next=protected-access  # reason: a successor cannot bypass an unretired input owner
        if row["state"] not in _STOPPED or row["id"] in self.runtime._leases:
            raise AgentTaskError("recovery requires a stopped task with no active input owner")
        if row["spec"]["mode"] != "skill" or not row["spec"]["actions"]:
            raise AgentTaskError("recovery requires a finite skill workflow")
        with self.runtime.store.connection() as connection:
            reviews = [dict(item) for item in connection.execute(
                "SELECT * FROM agent_reviews WHERE task_id=? ORDER BY action_id", (row["id"],))]
        return self.runtime.store.actions(row["id"]), reviews

    def _template(self, row: dict) -> dict:
        spec = detached(row["spec"])
        spec["goal"] = "Reviewed remainder: " + spec["goal"][:15940]
        spec["options"].pop("skill_pin", None)
        # pylint: disable-next=protected-access  # reason: the shared host policy must normalize every review template
        return self.runtime._validated_spec(spec).to_dict()

    def _preview(self, row: dict, receipts: list[dict], reviews: list[dict]) -> dict:
        active = effective_actions(receipts)
        template = self._template(row)
        source = AgentTaskSpec.from_dict(row["spec"])
        issues = _source_issues(source, active)
        completed = len(active) if not issues else None
        remaining = detached(source.actions[len(active):])
        issues.extend(_action_issues(remaining))
        if not remaining:
            issues.append("no_remaining_actions")
        template["actions"] = remaining
        return {"source_task": row["id"], "snapshot": _snapshot(row, receipts, reviews),
                "source_state": row["state"], "completed_steps": completed, "attempted_steps": len(active),
                "remaining_actions": remaining,
                "rows": row_report(source, receipts), "issues": sorted(set(issues)),
                "source_receipts": [{key: item[key] for key in ("id", "command", "status")}
                                    for item in receipts[:200]], "source_receipt_total": len(receipts),
                "draft": template if not issues else None, "approval_required": True,
                "source_completion_inherited": False}

    def _create(self, row: dict, request: dict) -> dict:
        note = request["note"]
        if not isinstance(note, str) or not note.strip() or len(note) > 4000:
            raise AgentTaskError("recovery requires a bounded operator review note")
        # pylint: disable-next=protected-access  # reason: reviewed successors use the same live host scope validation
        spec = self.runtime._validated_spec(request["spec"])
        _check_scope(self._template(row), spec.to_dict())
        _require_actions(spec)
        existing = self._existing(row["id"], request["snapshot"], durable_payload(spec.to_dict()))
        if existing is not None:
            return existing
        receipts, reviews = self._read(row)
        if request["snapshot"] != _snapshot(row, receipts, reviews):
            raise AgentTaskError("source recovery snapshot changed; preview and review again")
        if any(item["status"] not in {"confirmed", "not_applied", "failed"} for item in receipts):
            raise AgentTaskError("reconcile unknown source effects before creating a successor")
        # pylint: disable-next=protected-access  # reason: atomically bind lineage through the shared task creator
        task = self.runtime._create_task(spec, None, recovery=(row["id"], request["snapshot"], note))
        return {"task_id": task.task_id, "state": task.state,
                "recovery": recovery_link(self.runtime.store, task.task_id)}

    def _existing(self, source: str, snapshot: Any, spec: dict) -> dict | None:
        with self.runtime.store.connection() as connection:
            record = connection.execute("SELECT task_id,snapshot FROM agent_task_recoveries WHERE source_task=?",
                                        (source,)).fetchone()
        if record is None:
            return None
        # pylint: disable-next=protected-access  # reason: an idempotent retry still requires ownership of its successor
        child = self.runtime._row(record["task_id"])
        if record["snapshot"] != snapshot or child["spec"] != spec:
            raise AgentTaskError("source already has a different reviewed successor")
        self.runtime.evidence.ensure(child["id"])
        return {"task_id": child["id"], "state": child["state"],
                "recovery": recovery_link(self.runtime.store, child["id"])}


def _snapshot(row: dict, receipts: list[dict], reviews: list[dict]) -> str:
    return request_spec_digest({"task": row, "actions": receipts, "reviews": reviews})


def _require_operator() -> None:
    identity = current_authorization()
    if identity is not None and not identity.allows(Capability.DRIVE_INPUT):
        raise AuthorizationError("reviewing task recovery requires drive_input")


def _source_issues(spec: AgentTaskSpec, receipts: list[dict]) -> list[str]:
    if any(item["status"] != "confirmed" for item in receipts):
        return ["unknown_source_effects"]
    try:
        return [] if verified_prefix(spec, receipts) else ["source_readback_mismatch"]
    except (KeyError, TypeError, ValueError, AgentTaskError):
        return ["source_readback_mismatch"]


def _capture_names(value: Any) -> set[str]:
    if isinstance(value, dict):
        names = _capture_reference(value)
        return names.union(*(_capture_names(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_capture_names(item) for item in value))
    return set()


def _capture_reference(value: dict) -> set[str]:
    if "$capture" not in value:
        return set()
    if set(value) - {"$capture", "transform"} or not isinstance(value["$capture"], str) or not value["$capture"]:
        raise AgentTaskError("capture references require a fresh named capture")
    _check_transform(value.get("transform", "identity"))
    return {value["$capture"]}


def _action_issues(actions: list[dict]) -> list[str]:
    available: set[str] = set()
    issues = []
    for action in actions:
        if action.get("reference") is not None or "observation_id" in action or action.get("tool") in _POINTER_TOOLS:
            issues.append("fresh_semantic_grounding_required")
        needed = _capture_names(action.get("arguments", {}))
        if "expect_capture" in action:
            name = action["expect_capture"]
            if not isinstance(name, str) or not name:
                raise AgentTaskError("expected capture must name a fresh workflow capture")
            needed.add(name)
        if needed - available:
            issues.append("fresh_capture_required")
        available.update(_capture_declaration(action))
    return issues


def _capture_declaration(action: dict) -> set[str]:
    if "capture" not in action:
        return set()
    if not isinstance(action["capture"], str) or not action["capture"]:
        raise AgentTaskError("capture must be a nonempty fresh name")
    return {action["capture"]}


def _check_transform(operation: Any) -> None:
    if not isinstance(operation, str):
        raise AgentTaskError("workflow transformation must be a reviewed name")
    transformed("", operation)


def _check_scope(template: dict, reviewed: dict) -> None:
    fixed = set(template) - {"goal", "actions"}
    if any(request_spec_digest({"value": template[key]}) != request_spec_digest({"value": reviewed[key]})
           for key in fixed):
        raise AgentTaskError("recovery must preserve source scope, inputs, budgets and completion criteria")


def _require_actions(spec: AgentTaskSpec) -> None:
    actions = spec.to_dict()["actions"]
    if not actions or len(actions) > spec.budget.max_steps or _action_issues(actions):
        raise AgentTaskError("review fresh semantic actions and captures before creating a successor")
    for action in actions:
        _check_transform(action.get("transform", "identity"))
        if set(action) - {"tool", "arguments", "capture", "expect_capture", "expect_result", "expect_not_result",
                          "transform", "row"}:
            raise AgentTaskError("recovery action contains unreviewed fields")
        if action.get("tool") not in spec.allowed_tools or not isinstance(action.get("arguments", {}), dict):
            raise AgentTaskError("recovery actions must use the source's reviewed tools and named arguments")
