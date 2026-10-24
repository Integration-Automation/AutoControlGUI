"""Explicit post-effect completion review with private lineage and permanent read-only targets."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError, AgentHumanReview
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.policy import TaskPolicy, owns_task
from je_auto_control.utils.agent_runtime.receipts import effective_actions
from je_auto_control.utils.agent_runtime.task_authority import (
    CompletionBinding, ownership_review, public_ownership, recovery_binding,
)
from je_auto_control.utils.agent_runtime.workflow_values import complete
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

_STOPPED = frozenset({"paused", "waiting_user", "recovering", "cancelled", "timed_out", "failed"})
_INDEPENDENT = frozenset({"file_exists", "file_text", "file_sha256", "file_manifest", "screen", "browser"})


def completion_details(store: Any, task_id: str) -> dict | None:
    """Read private host admission; user specification options never grant this authority."""
    with store.connection() as connection:
        row = connection.execute("SELECT details FROM agent_readonly_completions WHERE task_id=?",
                                 (task_id,)).fetchone()
    return json.loads(row[0]) if row is not None else None


def _snapshot(runtime: Any, row: dict) -> str:
    # pylint: disable-next=import-outside-toplevel  # reason: share the exact existing receipt/review snapshot contract
    from je_auto_control.utils.agent_runtime.task_recovery import _snapshot as source_snapshot
    with runtime.store.connection() as connection:
        reviews = [dict(item) for item in connection.execute(
            "SELECT * FROM agent_reviews WHERE task_id=? ORDER BY action_id", (row["id"],))]
    return source_snapshot(row, runtime.store.actions(row["id"]), reviews)


def _stopped(runtime: Any, row: dict) -> None:
    # pylint: disable-next=protected-access  # reason: completion cannot borrow live input or an unwinding operation
    if row["state"] not in _STOPPED or row["id"] in runtime._leases or row["id"] in runtime._executing:
        raise AgentTaskError("completion review requires stopped, retired source input")


def _principals(details: dict) -> None:
    reviewer = details["reviewer"]
    for owner in (details["source_owner"], details["effect_owner"]):
        with DeferredAuthorization(AuthorizationContext(**reviewer) if reviewer else None).scope():
            if not owns_task(owner, current_authorization()):
                raise AuthorizationError("completion reviewer can no longer manage the source owner")
        with DeferredAuthorization(AuthorizationContext(**owner) if owner else None).scope():
            pass


def check_completion_authority(runtime: Any, task_id: str) -> None:
    """Keep source/effect snapshots and both real principals live through reads and success publication."""
    details = completion_details(runtime.store, task_id)
    if details is None:
        return
    _principals(details)
    for name in ("source", "effect"):
        row = runtime.store.get(details[name + "_task"])
        _stopped(runtime, row)
        if _snapshot(runtime, row) != details[name + "_snapshot"]:
            raise AgentHumanReview("completion source snapshot changed; review completion again")
    effect = runtime.store.get(details["effect_task"])
    TaskPolicy(AgentTaskSpec.from_dict(effect["spec"])).validate_snapshot()


def completion_metadata(store: Any, task_id: str) -> dict:
    """Expose bounded public provenance without private principal stores or authority-bearing fields."""
    details = completion_details(store, task_id)
    if details is None:
        return {}
    return {"completion_review": {"contract": 1, "source_task": details["source_task"],
                                  "effect_task": details["effect_task"], "snapshot": details["source_snapshot"]}}


def completion_target(runtime: Any, row: Mapping, original: Any) -> Any:
    """Select a separately owned read-only proxy from private admission, never from model-authored options."""
    if completion_details(runtime.store, row["id"]) is None:
        return original
    # pylint: disable-next=protected-access  # reason: cache is private runtime-owned adapter lifecycle state
    cache = runtime._completion_targets
    # pylint: disable-next=protected-access  # reason: target cache belongs to the runtime's task/cleanup lifecycle
    with runtime._mutex:
        cached = cache.get(row["id"])
        if cached is None:
            # pylint: disable-next=import-outside-toplevel  # reason: only privately admitted tasks need this adapter
            from je_auto_control.utils.agent_runtime.readonly_target import new_completion_target
            _require_target(original)
            cached = new_completion_target(original)
            cache[row["id"]] = cached
        return cached


def completion_evidence(runtime: Any, row: dict) -> tuple[TaskPolicy, list[dict]]:
    """Verify original pinned action evidence, while the task's target supplies a fresh independent observation."""
    details = completion_details(runtime.store, row["id"])
    effect = runtime.store.get(details["effect_task"]) if details is not None else row
    check_completion_authority(runtime, row["id"])
    return TaskPolicy(AgentTaskSpec.from_dict(effect["spec"])), runtime.store.actions(effect["id"])


def require_executable_task(store: Any, task_id: str) -> None:
    """Refuse action preparation and ordinary successors before any input or helper startup."""
    if completion_details(store, task_id) is not None:
        raise AgentTaskError("read-only completion tasks require explicit completion review, never executable actions")


def _require_target(adapter: Any) -> None:
    # pylint: disable-next=unidiomatic-typecheck  # reason: no custom capability descriptor or helper is trusted implicitly
    if type(adapter) is not NativeDesktopTarget or not adapter.supports_readonly_completion:
        raise AgentTaskError("target has no supported permanent read-only completion helper")


def _effect(runtime: Any, row: dict) -> dict:
    details = completion_details(runtime.store, row["id"])
    effect = runtime.store.get(details["effect_task"]) if details is not None else row
    _stopped(runtime, effect)
    spec = AgentTaskSpec.from_dict(effect["spec"])
    receipts = runtime.store.actions(effect["id"])
    try:
        planned = complete(spec, effective_actions(receipts)) if spec.mode == "skill" else not spec.actions
    except (LookupError, TypeError, ValueError):
        planned = False
    if not planned or any(item["status"] not in {"confirmed", "not_applied", "failed"} for item in receipts):
        raise AgentTaskError("completion review requires all finite source actions confirmed")
    if not any(item.get("kind") in _INDEPENDENT for item in spec.success_criteria):
        raise AgentTaskError("completion review requires independent fresh completion criteria")
    return effect


def completion_spec(runtime: Any, effect: dict) -> AgentTaskSpec:
    """Derive the exact no-action verification scope shared by admission and evidence consumers."""
    spec = detached(effect["spec"])
    spec.update(goal="Reviewed completion: " + spec["goal"][:15940], mode="external", actions=[])
    for key in ("dag_batch", "skill_pin"):
        spec["options"].pop(key, None)
    # pylint: disable-next=protected-access  # reason: retain current host profile, scope and criteria validation
    return runtime._validated_spec(spec)


def _details(runtime: Any, source: dict, effect: dict, ownership: dict | None) -> dict:
    actor = current_authorization()
    reviewer = ownership["actor"] if ownership is not None else (asdict(actor) if actor else {})
    details = {"contract": 1, "source_task": source["id"], "source_snapshot": _snapshot(runtime, source),
               "effect_task": effect["id"], "effect_snapshot": _snapshot(runtime, effect),
               "reviewer": reviewer, "source_owner": source["owner"], "effect_owner": effect["owner"]}
    _principals(details)
    return details


def control_completion(recovery: Any, operation: str, row: dict, request: dict, ownership: dict | None) -> dict:
    """Review a deterministic read-only successor or atomically admit its exact source snapshot once."""
    runtime = recovery.runtime
    _stopped(runtime, row)
    effect = _effect(runtime, row)
    # pylint: disable-next=protected-access  # reason: inspect only the host-configured original adapter, without probing
    _require_target(runtime._targets.get(effect["spec"]["target"]))
    spec = completion_spec(runtime, effect)
    details = _details(runtime, row, effect, ownership)
    owned = ownership_review(ownership, details["source_snapshot"])
    if operation == "preview_completion":
        result = {"source_task": row["id"], "effect_task": effect["id"], "snapshot": details["source_snapshot"],
                  "approval_required": True, "source_completion_inherited": False, "verification_spec": spec.to_dict()}
        if owned is not None:
            result["ownership"] = public_ownership(owned)
        return result
    if request["snapshot"] != details["source_snapshot"]:
        raise AgentTaskError("completion source snapshot changed; preview and review again")
    if owned is not None and request["ownership_review"] != owned["review"]:
        raise AgentTaskError("completion ownership changed; review again")
    return _create(recovery, row, request, spec, details, owned)


def _create(recovery: Any, row: dict, request: dict, spec: AgentTaskSpec, details: dict, owned: dict | None) -> dict:
    # pylint: disable-next=import-outside-toplevel  # reason: reuse bounded human review and provenance projection
    from je_auto_control.utils.agent_runtime.task_recovery import _review_note, recovery_link
    note = _review_note(request["note"])
    runtime = recovery.runtime
    # pylint: disable-next=protected-access  # reason: the shared recovery retry gate checks ownership and exact scope
    existing = recovery._existing(row["id"], request["snapshot"], spec.to_dict(), ownership=owned)
    if existing is not None:
        actual = completion_details(runtime.store, existing["task_id"])
        if actual != details:
            raise AgentTaskError("source already has a different completion review")
        return existing
    # pylint: disable-next=protected-access  # reason: atomic private proof and real lineage share the task transaction
    task = runtime._create_task(spec, None, recovery=(row["id"], request["snapshot"], note),
                                authorization=CompletionBinding(recovery_binding(None, owned), details))
    return {"task_id": task.task_id, "state": task.state, "recovery": recovery_link(runtime.store, task.task_id)}
