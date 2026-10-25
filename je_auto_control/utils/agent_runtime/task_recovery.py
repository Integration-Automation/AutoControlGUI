"""Review stopped tasks and create one explicitly approved successor without replay."""
from __future__ import annotations

from typing import Any
import json

from je_auto_control.utils.agent_runtime.errors import AgentTaskError, AgentHumanReview
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.policy import durable_payload, owns_task, TaskPolicy, validate_root_snapshot
from je_auto_control.utils.agent_runtime.receipts import effective_actions, row_report
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.agent_runtime.task_authority import (
    validate_ownership_request, ownership_scope, ownership_review, public_ownership,
    recovery_binding, require_matching_ownership,
    check_recovery_authority,
    check_handoff_history, HandoffScope, check_historical_recovery_identity,
)
from je_auto_control.utils.agent_runtime.evidence_handoff import EvidenceHandoffs, OPERATIONS as HANDOFF_OPERATIONS
from je_auto_control.utils.agent_runtime.handoff_records import HandoffRecords, HandoffAccess, standalone_handoff
from je_auto_control.utils.agent_runtime.task_handoff import TaskHandoffContext
from je_auto_control.utils.agent_runtime.recovery_authorization import (
    prepare_authorization, authorized_template, narrowed_template, authorization_details, _intersect,
)
from je_auto_control.utils.agent_runtime.workflow_values import verified_prefix, transformed
from je_auto_control.utils.rbac.authorization import current_authorization, AuthorizationError
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.users import Capability

_REQUEST_FIELDS = {
    "preview": {"task_id"}, "create": {"task_id", "snapshot", "spec", "note"},
    "review_authorization": {"task_id"},
    "create_authorized": {"task_id", "snapshot", "spec", "note", "authorization_review"},
    "preview_completion": {"task_id"}, "create_completion": {"task_id", "snapshot", "note"},
    "review_completion_authorization": {"task_id"},
    "create_authorized_completion": {"task_id", "snapshot", "authorization_review", "note"},
}
OPERATIONS = tuple(_REQUEST_FIELDS) + HANDOFF_OPERATIONS
_STOPPED = frozenset({"paused", "waiting_user", "recovering", "cancelled", "timed_out", "failed"})
_POINTER_TOOLS = ("AC_click_mouse", "AC_set_mouse_position", "AC_mouse_scroll", "AC_press_mouse", "AC_release_mouse",
                  "AC_android_tap", "AC_android_swipe")


def recovery_link(store: Any, task_id: str) -> dict:
    """Return durable successor provenance, without treating the source as completed."""
    with store.connection() as connection:
        row = connection.execute("SELECT r.source_task,r.snapshot,r.note,r.created,a.details,o.details AS ownership "
                                 "FROM agent_task_recoveries r LEFT JOIN agent_task_authorizations a "
                                 "ON a.task_id=r.task_id LEFT JOIN agent_recovery_owners o "
                                 "ON o.task_id=r.task_id WHERE r.task_id=?", (task_id,)).fetchone()
    if row is None:
        return {}
    result = dict(row)
    details = result.pop("details")
    ownership = result.pop("ownership")
    if details is not None:
        result["reauthorization"] = json.loads(details)
    if ownership is not None:
        result["ownership"] = public_ownership(json.loads(ownership))
    return result


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

    def _handoffs(self, *, standalone: bool = False) -> EvidenceHandoffs:
        context = (TaskHandoffContext(self.runtime, self._handoff_snapshot, check_historical_recovery_identity,
                                     request_spec_digest, owns_task).context if standalone
                   else self.runtime.batches.handoff_context)
        return EvidenceHandoffs(self.runtime, context, self.handoff_witness, self.handoff_scope,
                                HandoffRecords(standalone))

    def _handoffs_for(self, operation: str, request: dict) -> EvidenceHandoffs:
        # pylint: disable-next=protected-access  # reason: resolve no private storage family after service shutdown
        if self.runtime._closed:
            raise AgentTaskError('runtime is closed')
        standalone = 'source_task' in request
        if operation in {'get_handoff', 'revoke_handoff'} and isinstance(request.get('handoff_id'), str):
            with self.runtime.store.connection() as connection:
                standalone = standalone_handoff(connection, request['handoff_id'])
        return self._handoffs(standalone=standalone)

    def task_handoff_evidence(self, source_task: str, task_id: str, handoff_id: str,
                              *, connection: Any = None) -> HandoffAccess:
        """Adopt only a validated explicit non-DAG projection without ordinary task access."""
        return self._handoffs(standalone=True).consume_task(source_task, task_id, handoff_id, connection=connection)

    def handoff_scope(self, connection: Any, context: dict, links: list, issuer_policies: list[str] | None,
                      authorization: dict | None, *, issuing: bool = False) -> dict:
        """Derive historical input policy or explicitly reviewed read-only evidence policy on the host."""
        # pylint: disable-next=import-outside-toplevel  # reason: only explicit handoff proof needs completion renewal validation
        from je_auto_control.utils.agent_runtime.completion_recovery import handoff_completion_scope
        approved = handoff_completion_scope(self.runtime, connection, context, links,
                                             authorization=authorization, issuing=issuing)
        if approved is not None:
            return approved
        if authorization is not None:
            raise AgentTaskError('renewed handoff completion authorization is unavailable')
        if context['binding'].get('kind') == 'task_completion':
            return {'policy': self._task_handoff_policy(context, links, issuer_policies), 'evidence_scope': True}
        return {'policy': self.runtime.batches.handoff_policy(context['source'], issuer_policies)}

    def _task_handoff_policy(self, context: dict, links: list, issuer_policies: list[str] | None) -> TaskPolicy:
        template = detached(context['source']['spec'])
        origins = set(issuer_policies or [])
        for row in (links[0][0], *(child for _source, child, _link in links)):
            validate_root_snapshot(row['spec']['roots'])
            if template['roots'] and row['spec']['roots']:
                template['roots'] = _intersect(template['roots'], row['spec']['roots'])
                if not template['roots']:
                    raise AgentTaskError('handoff has no shared historical root scope')
            origins.update(row['spec']['options'].get('origin_policies', []))
        template['options']['origin_policies'] = sorted(origins)
        # pylint: disable-next=protected-access  # reason: current host/session and all live historical origins still apply
        return TaskPolicy(self.runtime._validated_spec(template))

    def handoff_evidence(self, batch_id: str, node_id: str, source_task: str,
                         task_id: str, handoff_id: str, *, connection: Any = None) -> tuple[dict, list]:
        """Read one explicitly granted completion projection without changing ordinary runtime access."""
        return self._handoffs().consume(batch_id, node_id, source_task, task_id, handoff_id, connection=connection)

    def handoff_snapshot(self, connection: Any, row: dict) -> dict:
        """Supply the existing private task/completion snapshot to host-owned evidence collaborators."""
        return self._handoff_snapshot(connection, row)

    def _handoff_snapshot(self, connection: Any, row: dict) -> dict:
        actions = self.runtime.store.read_actions(connection, row['id'])
        reviews = [dict(item) for item in connection.execute(
            'SELECT * FROM agent_reviews WHERE task_id=? ORDER BY action_id', (row['id'],))]
        retired = connection.execute('SELECT contract,confirmed FROM agent_completion WHERE task_id=?',
                                     (row['id'],)).fetchone()
        snapshot = _snapshot(row, actions, reviews)
        return {'actions': actions, 'snapshot': snapshot, 'completion_snapshot': request_spec_digest({
            'snapshot': snapshot, 'retirement': dict(retired) if retired is not None else None})}

    def handoff_witness(self, connection: Any, source: dict, child: dict, link: dict, *, scope: Any = None) -> dict:
        """Bind real historical recovery snapshots and current authority without target probes."""
        before, after = self._handoff_snapshot(connection, source), self._handoff_snapshot(connection, child)
        evidence = {'source_snapshot': before['snapshot'], 'source_actions': before['actions'],
                    'snapshot': after['snapshot'], 'actions': after['actions'],
                    'completion_snapshot': after['completion_snapshot']}
        def reader(active: Any, parent: dict, task: dict) -> Any:
            return self._handoff_reader(active, parent, task, scope=scope)
        check_handoff_history(self.runtime, connection, source, child, link, evidence, reader)
        return evidence

    def _handoff_reader(self, connection: Any, source: dict, child: dict, *, scope: Any = None) -> bool | HandoffScope:
        # pylint: disable-next=import-outside-toplevel  # reason: reuse privately admitted read-only scope without a reverse import
        from je_auto_control.utils.agent_runtime.completion_recovery import check_completion_authority, completion_spec
        if scope is not None:
            # pylint: disable-next=import-outside-toplevel  # reason: historical private readers are checked without reviving old grants
            from je_auto_control.utils.agent_runtime.completion_recovery import historical_handoff_reader
            return HandoffScope(scope, historical_handoff_reader(self.runtime, connection, source),
                                historical_handoff_reader(self.runtime, connection, child))
        # pylint: disable-next=import-outside-toplevel  # reason: share strict neutral binding decoding, not public caller options
        from je_auto_control.utils.agent_runtime.skill_completion import _decode_binding
        found = connection.execute('SELECT details FROM agent_readonly_completions WHERE task_id=?',
                                   (child['id'],)).fetchone()
        if found is None:
            return False
        details = _decode_binding(found[0])
        if details['source_task'] != source['id']:
            raise AgentTaskError('handoff read-only source binding changed')
        check_completion_authority(self.runtime, child['id'], connection=connection)
        effect = self.runtime.store.read_task(connection, details['effect_task'])
        if child['spec'] != completion_spec(self.runtime, effect).to_dict():
            raise AgentTaskError('handoff read-only verification scope changed')
        return True

    def review_evidence(self, connection: Any, source: dict, child: dict, link: dict) -> dict:
        """Read exact source/child snapshots for skill publication without input or clock renewal."""
        # pylint: disable-next=protected-access  # reason: do not adopt live or unwinding source/child input
        with self.runtime._mutex:
            # pylint: disable-next=protected-access  # reason: inspect only this runtime's private retirement witnesses
            if any(row['id'] in self.runtime._leases or row['id'] in self.runtime._executing
                   for row in (source, child)):
                raise AgentTaskError('execution evidence input has not retired')
        if child['state'] not in _STOPPED | {'succeeded'}:
            raise AgentTaskError('execution evidence requires a retired successor')
        actions, reviews = self._read(source)
        source_snapshot = _snapshot(source, actions, reviews)
        if source_snapshot != link['snapshot']:
            raise AgentHumanReview('execution source snapshot changed; review the full chain again')
        check_recovery_authority(self.runtime, connection, source, child, link)
        child_actions = self.runtime.store.actions(child['id'])
        child_reviews = [dict(row) for row in connection.execute(
            'SELECT * FROM agent_reviews WHERE task_id=? ORDER BY action_id', (child['id'],))]
        snapshot = _snapshot(child, child_actions, child_reviews)
        retired = connection.execute('SELECT contract,confirmed FROM agent_completion WHERE task_id=?',
                                     (child['id'],)).fetchone()
        return {'source_snapshot': source_snapshot, 'snapshot': snapshot,
                'completion_snapshot': request_spec_digest({'snapshot': snapshot,
                    'retirement': dict(retired) if retired is not None else None}),
                'source_actions': actions, 'actions': child_actions}

    def control(self, operation: str, request: Any = None) -> dict:
        """Preview without target access, or create an owner-scoped, deduplicated successor."""
        request = durable_payload(detached(request))
        if not isinstance(operation, str) or operation not in OPERATIONS or not isinstance(request, dict):
            raise AgentTaskError("invalid recovery operation fields")
        if operation in HANDOFF_OPERATIONS:
            return self._handoffs_for(operation, request).control(operation, request)
        validate_ownership_request(operation, request, _REQUEST_FIELDS[operation])
        task_id = request["task_id"]
        if not isinstance(task_id, str) or not task_id:
            raise AgentTaskError("recovery requires a task_id")
        # pylint: disable-next=protected-access  # reason: trusted lifecycle collaborator uses the runtime's task lock
        with self.runtime._lock(task_id), DeferredAuthorization.capture().scope():
            _require_operator()
            # pylint: disable-next=protected-access  # reason: reuse the runtime's owner and closed-state check
            row = self.runtime._row(task_id)
            with ownership_scope(row, request) as ownership:
                if operation in {"preview_completion", "create_completion", "review_completion_authorization",
                                 "create_authorized_completion"}:
                    # pylint: disable-next=import-outside-toplevel  # reason: independent completion uses a closed collaborator
                    from je_auto_control.utils.agent_runtime.completion_recovery import control_completion
                    return control_completion(self, operation, row, request, ownership)
                if operation in {"create", "create_authorized"}:
                    return self._create(row, request, ownership)
                receipts, reviews = self._read(row)
                return self._preview(row, receipts, reviews, reauthorize=operation == "review_authorization",
                                     ownership=ownership)

    def _read(self, row: dict) -> tuple[list[dict], list[dict]]:
        # pylint: disable-next=protected-access  # reason: a successor cannot bypass an unretired input owner
        if row["state"] not in _STOPPED or row["id"] in self.runtime._leases:
            raise AgentTaskError("recovery requires a stopped task with no active input owner")
        if row["spec"]["mode"] == "skill" and not row["spec"]["actions"]:
            raise AgentTaskError("recovery requires a finite skill workflow")
        with self.runtime.store.connection() as connection:
            reviews = [dict(item) for item in connection.execute(
                "SELECT * FROM agent_reviews WHERE task_id=? ORDER BY action_id", (row["id"],))]
        return self.runtime.store.actions(row["id"]), reviews

    def _template(self, row: dict, authorization: dict | None = None) -> dict:
        spec = detached(row["spec"])
        spec["goal"] = "Reviewed remainder: " + spec["goal"][:15940]
        spec["options"].pop("skill_pin", None)
        if spec["mode"] != "skill":
            spec["actions"] = []
        if authorization is not None:
            spec = authorized_template(spec, authorization)
        # pylint: disable-next=protected-access  # reason: the shared host policy must normalize every review template
        return self.runtime._validated_spec(spec).to_dict()

    def _preview(self, row: dict, receipts: list[dict], reviews: list[dict], *, reauthorize: bool = False,
                 ownership: dict | None = None) -> dict:
        active = effective_actions(receipts)
        source = AgentTaskSpec.from_dict(row["spec"])
        snapshot = _snapshot(row, receipts, reviews)
        authorization = prepare_authorization(source, snapshot) if reauthorize else None
        result = {"source_task": row["id"], "snapshot": snapshot,
                "source_state": row["state"], "source_mode": source.mode, "attempted_steps": len(active),
                "source_receipts": [{key: item[key] for key in ("id", "command", "status")}
                                    for item in receipts[:200]], "source_receipt_total": len(receipts),
                "approval_required": True, "source_completion_inherited": False}
        owned = ownership_review(ownership, snapshot)
        if owned is not None:
            result["ownership"] = public_ownership(owned)
        if authorization is not None:
            result.update(authorization_review=authorization["review"], authorization=authorization["context"],
                          existing_successor=_successor(self.runtime.store, row["id"]))
        try:
            template = self._template(row, authorization)
        except AgentTaskError:
            if authorization is None:
                raise
            return {**result, "draft": None, "review_template": None, "remaining_actions": [], "rows": [],
                    "completed_steps": None, "issues": ["authorization_scope_unavailable"]}
        result.update(_review_plan(source, receipts, active, template))
        if authorization is not None:
            self._review_authorized_actions(result, template)
        return result

    def _review_authorized_actions(self, result: dict, template: dict) -> None:
        if result["source_mode"] != "skill":
            return
        candidate = result["draft"]
        if candidate is None:
            result["review_template"] = {**template, "actions": result["remaining_actions"]}
            return
        try:
            # pylint: disable-next=protected-access  # reason: a narrowed preview cannot claim stale file actions are valid
            self.runtime._validated_spec(candidate)
        except AgentTaskError:
            result.update(draft=None, review_template=candidate)
            result["issues"].append("action_scope_requires_review")

    def _creation_scope(self, row: dict, request: dict) -> tuple[dict, dict | None]:
        if "authorization_review" not in request:
            return self._template(row), None
        authorization = prepare_authorization(AgentTaskSpec.from_dict(row["spec"]), request["snapshot"])
        if authorization["review"] != request["authorization_review"]:
            raise AgentTaskError("source authorization context changed; review authorization again")
        return self._template(row, authorization), authorization

    def _create(self, row: dict, request: dict, ownership: dict | None = None) -> dict:
        # pylint: disable-next=import-outside-toplevel  # reason: ordinary recovery cannot upgrade a read-only admission
        from je_auto_control.utils.agent_runtime.completion_recovery import require_executable_task
        require_executable_task(self.runtime.store, row["id"])
        note = _review_note(request["note"])
        ownership = ownership_review(ownership, request["snapshot"])
        if ownership is not None and request["ownership_review"] != ownership["review"]:
            raise AgentTaskError("recovery ownership changed; review the source owner again")
        template, authorization = self._creation_scope(row, request)
        # pylint: disable-next=protected-access  # reason: reviewed successors use the same live host scope validation
        spec = self.runtime._validated_spec(request["spec"])
        if authorization is not None:
            template = narrowed_template(template, spec.to_dict())
        _check_scope(template, spec.to_dict())
        _require_plan(spec)
        review = authorization["review"] if authorization is not None else None
        existing = self._existing(row["id"], request["snapshot"], durable_payload(spec.to_dict()), review, ownership)
        if existing is not None:
            return existing
        receipts, reviews = self._read(row)
        if request["snapshot"] != _snapshot(row, receipts, reviews):
            raise AgentTaskError("source recovery snapshot changed; preview and review again")
        if any(item["status"] not in {"confirmed", "not_applied", "failed"} for item in receipts):
            raise AgentTaskError("reconcile unknown source effects before creating a successor")
        details = authorization_details(authorization, spec) if authorization is not None else None
        # pylint: disable-next=protected-access  # reason: atomically bind lineage and authorization in the task creator
        task = self.runtime._create_task(spec, None, recovery=(row["id"], request["snapshot"], note),
                                         authorization=recovery_binding(details, ownership))
        return {"task_id": task.task_id, "state": task.state,
                "recovery": recovery_link(self.runtime.store, task.task_id)}

    def _existing(self, source: str, snapshot: Any, spec: dict, review: str | None = None,
                  ownership: dict | None = None) -> dict | None:
        with self.runtime.store.connection() as connection:
            record = connection.execute("SELECT task_id,snapshot FROM agent_task_recoveries WHERE source_task=?",
                                        (source,)).fetchone()
        if record is None:
            return None
        # pylint: disable-next=protected-access  # reason: an idempotent retry still requires ownership of its successor
        child = self.runtime._row(record["task_id"])
        require_matching_ownership(self.runtime.store, child["id"], ownership)
        link = recovery_link(self.runtime.store, child["id"])
        if (record["snapshot"] != snapshot or child["spec"] != spec
                or link.get("reauthorization", {}).get("review") != review):
            raise AgentTaskError("source already has a different reviewed successor")
        self.runtime.evidence.ensure(child["id"])
        return {"task_id": child["id"], "state": child["state"],
                "recovery": link}


def _snapshot(row: dict, receipts: list[dict], reviews: list[dict]) -> str:
    return request_spec_digest({"task": row, "actions": receipts, "reviews": reviews})


def _review_note(note: Any) -> str:
    if not isinstance(note, str) or not note.strip() or len(note) > 4000:
        raise AgentTaskError("recovery requires a bounded operator review note")
    return note


def _successor(store: Any, source: str) -> dict | None:
    with store.connection() as connection:
        row = connection.execute("SELECT task_id FROM agent_task_recoveries WHERE source_task=?", (source,)).fetchone()
    return {"task_id": row["task_id"], "recovery": recovery_link(store, row["task_id"])} if row is not None else None


def _require_operator() -> None:
    identity = current_authorization()
    if identity is not None and not identity.allows(Capability.DRIVE_INPUT):
        raise AuthorizationError("reviewing task recovery requires drive_input")


def _source_issues(spec: AgentTaskSpec, receipts: list[dict]) -> list[str]:
    if any(item["status"] != "confirmed" for item in receipts):
        return ["unknown_source_effects"]
    if spec.mode != "skill":
        return []
    try:
        return [] if verified_prefix(spec, receipts) else ["source_readback_mismatch"]
    except (KeyError, TypeError, ValueError, AgentTaskError):
        return ["source_readback_mismatch"]


def _review_plan(source: AgentTaskSpec, receipts: list[dict], active: list[dict], template: dict) -> dict:
    issues = _source_issues(source, active)
    if source.mode != "skill":
        template.update(goal="", actions=[])
        return {"completed_steps": None, "remaining_actions": [], "rows": [], "draft": None,
                "review_template": template, "issues": sorted(set(issues + ["new_plan_required"]))}
    completed = len(active) if not issues else None
    remaining = detached(source.actions[len(active):])
    issues.extend(_action_issues(remaining))
    if not remaining:
        issues.append("no_remaining_actions")
    template["actions"] = remaining
    return {"completed_steps": completed, "remaining_actions": remaining, "rows": row_report(source, receipts),
            "draft": template if not issues else None, "review_template": None, "issues": sorted(set(issues))}


def _require_plan(spec: AgentTaskSpec) -> None:
    if spec.mode == "skill":
        _require_actions(spec)
        return
    if spec.actions:
        raise AgentTaskError("dynamic recovery requires a reviewed goal without dormant finite actions")


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
