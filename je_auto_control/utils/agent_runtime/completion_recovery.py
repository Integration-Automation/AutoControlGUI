"""Explicit post-effect completion review with private lineage and permanent read-only targets."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.completion_contract import decode_completion_binding, decode_private_object
from je_auto_control.utils.agent_runtime.errors import AgentTaskError, AgentHumanReview
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.policy import TaskPolicy, owns_task
from je_auto_control.utils.agent_runtime.receipts import effective_actions
from je_auto_control.utils.agent_runtime.recovery_authorization import (
    prepare_authorization, authorized_template, authorization_details,
)
from je_auto_control.utils.agent_runtime.store import request_spec_digest
from je_auto_control.utils.agent_runtime.task_authority import (
    CompletionBinding, ownership_review, public_ownership, recovery_binding, check_historical_admission,
)
from je_auto_control.utils.agent_runtime.workflow_values import complete
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

_STOPPED = frozenset({"paused", "waiting_user", "recovering", "cancelled", "timed_out", "failed"})
_INDEPENDENT = frozenset({"file_exists", "file_text", "file_sha256", "file_manifest", "screen", "browser"})


def _connection(store: Any, connection: Any) -> Any:
    return store.connection() if connection is None else nullcontext(connection)


def completion_details(store: Any, task_id: str, *, connection: Any = None) -> dict | None:
    """Read private host admission; user specification options never grant this authority."""
    with _connection(store, connection) as reading:
        row = reading.execute("SELECT details FROM agent_readonly_completions WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            _missing_marker(reading, task_id)
            return None
    return decode_completion_binding(row[0])


def _missing_marker(connection: Any, task_id: str) -> None:
    row = connection.execute('SELECT details FROM agent_task_authorizations WHERE task_id=?', (task_id,)).fetchone()
    if row is None:
        return
    value = decode_private_object(row[0], 'invalid private recovery authorization')
    if value.get('kind') == 'readonly_completion':
        raise AgentTaskError('private read-only completion marker is missing')


def _snapshot(runtime: Any, row: dict, *, connection: Any = None) -> str:
    # pylint: disable-next=import-outside-toplevel  # reason: share the exact existing receipt/review snapshot contract
    from je_auto_control.utils.agent_runtime.task_recovery import _snapshot as source_snapshot
    with _connection(runtime.store, connection) as reading:
        actions = runtime.store.read_actions(reading, row['id'])
        reviews = [dict(item) for item in reading.execute(
            "SELECT * FROM agent_reviews WHERE task_id=? ORDER BY action_id", (row["id"],))]
    return source_snapshot(row, actions, reviews)


def _stopped(runtime: Any, row: dict, *, allow_verified: bool = False, connection: Any = None) -> None:
    # pylint: disable-next=protected-access  # reason: completion cannot borrow live input or an unwinding operation
    if row['state'] not in _STOPPED and not (allow_verified and _retired_reader(runtime, row, connection)):
        raise AgentTaskError('completion review requires stopped, retired source input')
    # pylint: disable-next=protected-access  # reason: even a durable completion cannot attest unwinding input
    if row['id'] in runtime._leases or row['id'] in runtime._executing:
        raise AgentTaskError("completion review requires stopped, retired source input")


def _retired_reader(runtime: Any, row: dict, connection: Any) -> bool:
    if row['state'] != 'succeeded':
        return False
    with _connection(runtime.store, connection) as reading:
        completion = reading.execute('SELECT contract FROM agent_completion WHERE task_id=?', (row['id'],)).fetchone()
        return (completion is not None and completion[0] == 1
                and completion_details(runtime.store, row['id'], connection=reading) is not None)


def _principals(details: dict) -> None:
    reviewer = details["reviewer"]
    for owner in (details["source_owner"], details["effect_owner"]):
        with DeferredAuthorization(AuthorizationContext(**reviewer) if reviewer else None).scope():
            if not owns_task(owner, current_authorization()):
                raise AuthorizationError("completion reviewer can no longer manage the source owner")
        with DeferredAuthorization(AuthorizationContext(**owner) if owner else None).scope():
            pass


def check_completion_authority(runtime: Any, task_id: str, *, connection: Any = None) -> dict | None:
    """Keep source/effect snapshots and both real principals live through reads and success publication."""
    details = completion_details(runtime.store, task_id, connection=connection)
    if details is None:
        return None
    _principals(details)
    with _connection(runtime.store, connection) as reading:
        for name in ("source", "effect"):
            row = runtime.store.read_task(reading, details[name + "_task"])
            _stopped(runtime, row, allow_verified=True, connection=reading)
            if _snapshot(runtime, row, connection=reading) != details[name + "_snapshot"]:
                raise AgentHumanReview("completion source snapshot changed; review completion again")
        child = runtime.store.read_task(reading, task_id)
        policy = TaskPolicy(_effect_spec(runtime, child, details, connection=reading))
        policy.validate_snapshot()
        authorization = _authorization(runtime.store, task_id, connection=reading)
        if authorization is not None:
            return {'verification_spec': child['spec'], 'effect_spec': policy.spec.to_dict(),
                    'authorization_review': authorization['review']}
    return None


def completion_metadata(store: Any, task_id: str, *, runtime: Any = None) -> dict:
    """Expose bounded public provenance without private principal stores or authority-bearing fields."""
    details = completion_details(store, task_id)
    if details is None:
        return {}
    result: dict = {"completion_review": {"contract": 1, "source_task": details["source_task"],
                                          "effect_task": details["effect_task"],
                                          "snapshot": details["source_snapshot"]}}
    with store.connection() as reading:
        renewed = reading.execute('SELECT 1 FROM agent_task_authorizations WHERE task_id=?', (task_id,)).fetchone()
    if runtime is not None and renewed is not None:
        try:
            check_completion_authority(runtime, task_id)
            result['completion_authorization'] = 'active'
        except (AuthorizationError, OSError, TypeError, ValueError, LookupError):
            result.update(completion_contract=0, completion_authorization='unavailable')
    return result


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
    spec = (_effect_spec(runtime, row, details) if details is not None
            else AgentTaskSpec.from_dict(effect['spec']))
    return TaskPolicy(spec), runtime.store.actions(effect["id"])


def require_executable_task(store: Any, task_id: str) -> None:
    """Refuse action preparation and ordinary successors before any input or helper startup."""
    if completion_details(store, task_id) is not None:
        raise AgentTaskError("read-only completion tasks require explicit completion review, never executable actions")


def _require_target(adapter: Any) -> None:
    # pylint: disable-next=unidiomatic-typecheck  # reason: no custom capability descriptor or helper is trusted implicitly
    if type(adapter) is not NativeDesktopTarget or not adapter.supports_readonly_completion:
        raise AgentTaskError("target has no supported permanent read-only completion helper")


def _effect(runtime: Any, row: dict, *, connection: Any = None) -> dict:
    details = completion_details(runtime.store, row["id"], connection=connection)
    with _connection(runtime.store, connection) as reading:
        effect = runtime.store.read_task(reading, details['effect_task']) if details is not None else row
        receipts = runtime.store.read_actions(reading, effect['id'])
    _stopped(runtime, effect)
    spec = AgentTaskSpec.from_dict(effect["spec"])
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
    # pylint: disable-next=protected-access  # reason: retain current host profile, scope and criteria validation
    return runtime._validated_spec(_verification_template(effect['spec']))


def _verification_template(value: dict) -> dict:
    spec = detached(value)
    spec.update(goal="Reviewed completion: " + spec["goal"][:15940], mode="external", actions=[])
    for key in ("dag_batch", "skill_pin"):
        spec["options"].pop(key, None)
    return spec


def _details(runtime: Any, source: dict, effect: dict, ownership: dict | None, *, connection: Any = None) -> dict:
    actor = current_authorization()
    reviewer = ownership["actor"] if ownership is not None else (asdict(actor) if actor else {})
    details = {"contract": 1, "source_task": source["id"],
               "source_snapshot": _snapshot(runtime, source, connection=connection),
               "effect_task": effect["id"], "effect_snapshot": _snapshot(runtime, effect, connection=connection),
               "reviewer": reviewer, "source_owner": source["owner"], "effect_owner": effect["owner"]}
    _principals(details)
    return details


def _review_mode(runtime: Any, row: dict, operation: str) -> bool:
    renewal = operation in {'review_completion_authorization', 'create_authorized_completion'}
    _stopped(runtime, row, allow_verified=renewal)
    if (not renewal and completion_details(runtime.store, row['id']) is not None
            and _authorization(runtime.store, row['id']) is not None):
        raise AgentTaskError('renewed read-only completion requires explicit completion authorization review')
    return renewal


def control_completion(recovery: Any, operation: str, row: dict, request: dict, ownership: dict | None) -> dict:
    """Review a deterministic read-only successor or atomically admit its exact source snapshot once."""
    runtime = recovery.runtime
    renewal = _review_mode(runtime, row, operation)
    effect = _effect(runtime, row)
    # pylint: disable-next=protected-access  # reason: inspect only the host-configured original adapter, without probing
    _require_target(runtime._targets.get(effect["spec"]["target"]))
    if renewal:
        spec, details, authorization = _renewal(runtime, row, ownership)
    else:
        spec, details, authorization = completion_spec(runtime, effect), _details(runtime, row, effect, ownership), None
    owned = ownership_review(ownership, details["source_snapshot"])
    if operation in {"preview_completion", 'review_completion_authorization'}:
        result = {"source_task": row["id"], "effect_task": effect["id"], "snapshot": details["source_snapshot"],
                  "approval_required": True, "source_completion_inherited": False, "verification_spec": spec.to_dict()}
        if owned is not None:
            result["ownership"] = public_ownership(owned)
        if authorization is not None:
            result.update(authorization_review=authorization['review'], authorization=authorization['context'])
        return result
    if request["snapshot"] != details["source_snapshot"]:
        raise AgentTaskError("completion source snapshot changed; preview and review again")
    if owned is not None and request["ownership_review"] != owned["review"]:
        raise AgentTaskError("completion ownership changed; review again")
    if authorization is not None and request['authorization_review'] != authorization['review']:
        raise AgentTaskError('completion authorization changed; review again')
    return _create(recovery, row, request, spec, details, owned, authorization)


def _create(recovery: Any, row: dict, request: dict, spec: AgentTaskSpec, details: dict, owned: dict | None,
            authorization: dict | None = None) -> dict:
    # pylint: disable-next=import-outside-toplevel  # reason: reuse bounded human review and provenance projection
    from je_auto_control.utils.agent_runtime.task_recovery import _review_note, recovery_link
    note = _review_note(request["note"])
    runtime = recovery.runtime
    # pylint: disable-next=protected-access  # reason: the shared recovery retry gate checks ownership and exact scope
    existing = recovery._existing(row["id"], request["snapshot"], spec.to_dict(),
                                  authorization['review'] if authorization is not None else None, owned)
    if existing is not None:
        if completion_details(runtime.store, existing['task_id']) != details:
            raise AgentTaskError("source already has a different completion review")
        return existing
    proof = ({**authorization_details(authorization, spec), 'kind': 'readonly_completion',
              'binding': authorization['context']['source_snapshot']} if authorization is not None else None)
    def validate(connection: Any) -> None:
        current = runtime.store.read_task(connection, row['id'])
        with DeferredAuthorization.capture().scope():
            actual = _renewal(runtime, current, owned, connection=connection)
        if (actual[0].to_dict(), actual[1], actual[2]) != (spec.to_dict(), details, authorization):
            raise AgentTaskError('completion source or authorization changed during creation')
    # pylint: disable-next=protected-access  # reason: atomic private proof and real lineage share the task transaction
    task = runtime._create_task(spec, None, recovery=(row["id"], request["snapshot"], note),
                                authorization=CompletionBinding(recovery_binding(proof, owned), details,
                                                                validate if authorization is not None else None))
    return {"task_id": task.task_id, "state": task.state, "recovery": recovery_link(runtime.store, task.task_id)}


def _renewal_base(runtime: Any, source: dict, effect: dict, *, connection: Any = None, depth: int = 0) -> dict:
    base = detached(effect['spec'])
    details = completion_details(runtime.store, source['id'], connection=connection)
    if details is not None:
        _historical_reader(runtime, source, details, effect, connection, depth)
        base['roots'] = list(source['spec']['roots'])
        origins = base['options'].get('origin_policies', []) + source['spec']['options'].get('origin_policies', [])
        base['options']['origin_policies'] = list(dict.fromkeys(origins))
    return base


def _authorized_effect(base: dict, authorization: dict) -> dict:
    approved = authorized_template(base, authorization)
    approved.update(actions=base['actions'], mode=base['mode'])
    return approved


def _renewal(runtime: Any, source: dict, ownership: dict | None, *, connection: Any = None) -> tuple:
    _stopped(runtime, source, allow_verified=True, connection=connection)
    effect = _effect(runtime, source, connection=connection)
    details = _details(runtime, source, effect, ownership, connection=connection)
    base = _renewal_base(runtime, source, effect, connection=connection)
    binding = _renewal_binding(runtime, details, connection=connection)
    authorization = prepare_authorization(AgentTaskSpec.from_dict(base), binding)
    spec = completion_spec(runtime, {**effect, 'spec': _authorized_effect(base, authorization)})
    return spec, details, authorization


def _authorization(store: Any, task_id: str, *, connection: Any = None) -> dict | None:
    with _connection(store, connection) as reading:
        row = reading.execute('SELECT details FROM agent_task_authorizations WHERE task_id=?', (task_id,)).fetchone()
    if row is None:
        return None
    value = decode_private_object(row[0], 'invalid private completion authorization', error_type=AgentHumanReview)
    if not _authorization_shape(value):
        raise AgentHumanReview('invalid private completion authorization')
    return value


def _authorization_shape(value: Any) -> bool:
    fields = {'review', 'context', 'approved_roots', 'actor', 'kind', 'binding'}
    context_fields = {'contract', 'source_snapshot', 'source_origins', 'replaced_origins', 'retained_origins',
                      'current_origins', 'source_roots', 'proposed_roots', 'policies'}
    if not isinstance(value, dict) or set(value) != fields or value['kind'] != 'readonly_completion':
        return False
    context = value['context']
    return (isinstance(context, dict) and set(context) == context_fields
            and _approval_shape(value) and _context_lists(context))


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _approval_shape(value: dict) -> bool:
    return (_string_list(value['approved_roots'])
            and all(isinstance(value[key], str) for key in ('review', 'binding', 'actor')))


def _context_lists(context: dict) -> bool:
    version = context['contract']
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        return False
    names = ('source_origins', 'replaced_origins', 'retained_origins', 'current_origins',
             'source_roots', 'proposed_roots')
    if not all(_string_list(context[name]) for name in names):
        return False
    return isinstance(context['policies'], list) and all(_policy_shape(policy) for policy in context['policies'])


def _policy_shape(value: Any) -> bool:
    return (isinstance(value, dict) and set(value) == {'id', 'roots'}
            and isinstance(value['id'], str) and _string_list(value['roots']))


def _effect_spec(runtime: Any, child: dict, details: dict, *, connection: Any = None,
                 historical: bool = False, depth: int = 0) -> AgentTaskSpec:
    with _connection(runtime.store, connection) as reading:
        effect = runtime.store.read_task(reading, details['effect_task'])
        authorization = _authorization(runtime.store, child['id'], connection=reading)
        source = runtime.store.read_task(reading, details['source_task'])
        base = _renewal_base(runtime, source, effect, connection=reading, depth=depth)
    if authorization is None:
        if (completion_details(runtime.store, source['id'], connection=connection) is not None
                and _authorization(runtime.store, source['id'], connection=connection) is not None):
            raise AgentHumanReview('renewed read-only history requires explicit completion authorization')
        return AgentTaskSpec.from_dict(effect['spec'])
    approved = _renewal_contract(authorization, base, _renewal_binding(runtime, details, connection=connection))
    if _verification_template(approved) != child['spec']:
        raise AgentHumanReview('completion authorized verification scope changed')
    if historical:
        return AgentTaskSpec.from_dict(approved)
    # pylint: disable-next=protected-access  # reason: current host/profile and caller ceilings still constrain old effects
    return runtime._validated_spec(approved)


def _renewal_contract(authorization: dict, base: dict, binding: str) -> dict:
    context = authorization['context']
    if (authorization['binding'] != binding or context['source_snapshot'] != binding
            or authorization['review'] != request_spec_digest(context)
            or context['source_roots'] != base['roots']
            or context['source_origins'] != base['options'].get('origin_policies', [])):
        raise AgentHumanReview('completion authorization or original binding changed')
    approved = _authorized_effect(base, authorization)
    if authorization['approved_roots'] != approved['roots']:
        raise AgentHumanReview('completion authorized verification scope changed')
    return approved


def _renewal_binding(runtime: Any, details: dict, *, connection: Any = None) -> str:
    admissions = []
    with _connection(runtime.store, connection) as reading:
        for identifier in dict.fromkeys((details['source_task'], details['effect_task'])):
            row = runtime.store.read_task(reading, identifier)
            check_historical_admission(reading, row)
            admission = reading.execute('SELECT a.*,b.owner AS batch_owner,b.graph_hash '
                'FROM agent_dag_local_tasks a JOIN agent_dag_batches b ON b.id=a.batch_id '
                'WHERE a.task_id=?', (identifier,)).fetchone()
            if admission is None and 'dag_batch' in row['spec']['options']:
                raise AgentHumanReview('completion original DAG admission evidence is missing')
            if admission is not None:
                admissions.append(dict(admission))
    return request_spec_digest({'completion': details, 'admissions': admissions})


def _historical_reader(runtime: Any, reader: dict, details: dict, effect: dict, connection: Any, depth: int) -> None:
    if depth >= 15:
        raise AgentTaskError('completion authorization exceeds sixteen real recovery links')
    _principals(details)
    with _connection(runtime.store, connection) as reading:
        _historical_link(runtime, reading, reader, details, effect)
        _stopped(runtime, reader, allow_verified=True, connection=reading)
        scope = _effect_spec(runtime, reader, details, connection=reading, historical=True, depth=depth + 1)
        if runtime.store.read_actions(reading, reader['id']):
            raise AgentHumanReview('read-only completion history contains executable receipts')
    expected = _verification_template(scope.to_dict())
    if _authorization(runtime.store, reader['id'], connection=connection) is None:
        before = set(expected['options'].get('origin_policies', []))
        after = reader['spec']['options'].get('origin_policies', [])
        if not before <= set(after):
            raise AgentHumanReview('completion historical origin scope changed')
        if after:
            expected['options']['origin_policies'] = after
    if expected != reader['spec']:
        raise AgentHumanReview('completion historical verification scope changed')


def _historical_link(runtime: Any, connection: Any, reader: dict, details: dict, effect: dict) -> None:
    link = connection.execute('SELECT source_task,snapshot FROM agent_task_recoveries WHERE task_id=?',
                               (reader['id'],)).fetchone()
    if (link is None or link['source_task'] != details['source_task']
            or link['snapshot'] != details['source_snapshot'] or details['effect_task'] != effect['id']):
        raise AgentHumanReview('completion historical binding changed')
    for name in ('source', 'effect'):
        row = runtime.store.read_task(connection, details[name + '_task'])
        _stopped(runtime, row, allow_verified=True, connection=connection)
        if _snapshot(runtime, row, connection=connection) != details[name + '_snapshot']:
            raise AgentHumanReview('completion historical source snapshot changed')
