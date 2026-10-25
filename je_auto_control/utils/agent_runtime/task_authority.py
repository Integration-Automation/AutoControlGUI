"""Trusted source-owner recovery admission and live owner/reviewer authority checks."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Iterator

from je_auto_control.utils.agent_runtime.dag_admission import actor_identity, check_admission
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.policy import owns_task, TaskPolicy
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization


@dataclass(frozen=True)
class RecoveryBinding:
    """An internal atomic envelope, never accepted as caller-authored JSON authority."""

    authorization: dict | None
    ownership: dict


@dataclass(frozen=True)
class CompletionBinding:
    """Host-derived read-only proof admitted atomically with the real recovery lineage."""

    recovery: dict | RecoveryBinding | None
    details: dict


def validate_ownership_request(operation: str, request: dict, fields: set[str]) -> None:
    """Accept an explicit source-owner policy and its reviewed token, never an arbitrary owner identity."""
    expected = set(fields)
    if "owner_policy" in request:
        if request["owner_policy"] != "source_owner":
            raise AgentTaskError("recovery owner_policy must be source_owner when supplied")
        expected.add("owner_policy")
        if operation in {"create", "create_authorized", "create_completion"}:
            expected.add("ownership_review")
    if set(request) != expected:
        raise AgentTaskError("invalid recovery operation fields")


@contextmanager
def ownership_scope(row: dict, request: dict) -> Iterator[dict | None]:
    """Bind explicit recovery to the current source owner, preserving the actual reviewer separately."""
    if "owner_policy" not in request:
        yield None
        return
    actor = current_authorization()
    owner = AuthorizationContext(**row["owner"]) if row["owner"] else None
    with DeferredAuthorization(owner).scope():
        resolved = current_authorization()
        value = {"contract": 1, "policy": "source_owner", "actor": asdict(actor) if actor else {},
                 "owner": asdict(resolved) if resolved else {}}
        _check_pair(value)
        yield value


def ownership_review(value: dict | None, snapshot: str) -> dict | None:
    """Freeze both identities and current roles against the reviewed source snapshot."""
    if value is None:
        return None
    data = {**value, "source_snapshot": snapshot}
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return {**data, "review": digest}


def public_ownership(value: dict) -> dict:
    """Project audit identity without exposing private user-store paths or input capabilities."""
    return {"contract": 1, "policy": value["policy"], "review": value["review"],
            "owner": value["owner"].get("user_id", "local"), "actor": value["actor"].get("user_id", "local")}


def recovery_binding(authorization: dict | None, ownership: dict | None) -> dict | RecoveryBinding | None:
    """Retain legacy authorization metadata while carrying trusted ownership into the same transaction."""
    if ownership is None:
        return authorization
    if authorization is not None:
        authorization = {**authorization, "actor": ownership["actor"].get("user_id", "local")}
    return RecoveryBinding(authorization, ownership)


def bind_recovery(connection: Any, task_id: str,
                  binding: dict | RecoveryBinding | CompletionBinding | None, owner: dict) -> None:
    """Atomically record ownership beside lineage and any separately reviewed origin renewal."""
    if isinstance(binding, CompletionBinding):
        connection.execute("INSERT INTO agent_readonly_completions VALUES (?,?)",
                           (task_id, json.dumps(binding.details)))
        binding = binding.recovery
    authorization = binding.authorization if isinstance(binding, RecoveryBinding) else binding
    if authorization is not None:
        connection.execute("INSERT INTO agent_task_authorizations VALUES (?,?)", (task_id, json.dumps(authorization)))
    if isinstance(binding, RecoveryBinding):
        if actor_identity(owner) != actor_identity(binding.ownership["owner"]):
            raise AgentTaskError("recovery ownership does not match the admitted task owner")
        _check_pair(binding.ownership)
        connection.execute("INSERT INTO agent_recovery_owners VALUES (?,?)", (task_id, json.dumps(binding.ownership)))


def require_matching_ownership(store: Any, task_id: str, expected: dict | None) -> None:
    """A retry cannot change the ownership policy, reviewer or source-owner review of an accepted child."""
    with store.connection() as connection:
        row = connection.execute("SELECT details FROM agent_recovery_owners WHERE task_id=?", (task_id,)).fetchone()
    actual = json.loads(row[0]) if row is not None else None
    if actual != expected:
        raise AgentTaskError("source already has a successor with a different ownership review")


def check_task_authority(runtime: Any, task_id: str) -> None:
    """Refresh local DAG claims and explicit recovery's owner/reviewer before managed input."""
    check_admission(runtime, task_id)
    with runtime.store.connection() as connection:
        row = connection.execute("SELECT details FROM agent_recovery_owners WHERE task_id=?", (task_id,)).fetchone()
    if row is not None:
        _check_pair(json.loads(row[0]))
    # pylint: disable-next=import-outside-toplevel  # reason: optional completion collaborator depends on this envelope
    from je_auto_control.utils.agent_runtime.completion_recovery import check_completion_authority
    check_completion_authority(runtime, task_id)


def _principal(value: Any) -> None:
    if not isinstance(value, dict):
        raise AgentTaskError('invalid recovery execution principal')
    if not value:
        return
    if not {'user_id', 'role'} <= set(value) or set(value) - {'user_id', 'role', 'store_path'}:
        raise AgentTaskError('invalid recovery execution principal')
    if (not all(isinstance(value[key], str) for key in ('user_id', 'role'))
            or value.get('store_path') is not None and not isinstance(value['store_path'], str)):
        raise AgentTaskError('invalid recovery execution principal')


def _recorded_owner(connection: Any, task_id: str) -> dict | None:
    row = connection.execute('SELECT details FROM agent_recovery_owners WHERE task_id=?', (task_id,)).fetchone()
    if row is None:
        return None
    try:
        value = json.loads(row[0])
    except (ValueError, TypeError) as error:
        raise AgentTaskError('invalid recovery execution ownership evidence') from error
    _ownership_contract(value)
    _principal(value['actor'])
    _principal(value['owner'])
    expected = ownership_review({key: item for key, item in value.items()
                                 if key not in {'source_snapshot', 'review'}}, value['source_snapshot'])
    if expected != value:
        raise AgentTaskError('recovery execution ownership review changed')
    return value


def _ownership_contract(value: Any) -> None:
    if (not isinstance(value, dict) or set(value) != {
            'contract', 'policy', 'actor', 'owner', 'source_snapshot', 'review'}):
        raise AgentTaskError('invalid recovery execution ownership contract')
    contract = value['contract']
    if (isinstance(contract, bool) or not isinstance(contract, int) or contract != 1
            or value['policy'] != 'source_owner'):
        raise AgentTaskError('invalid recovery execution ownership contract')


def check_recovery_authority(runtime: Any, connection: Any, source: dict, child: dict, link: dict) -> None:
    """Keep actual legacy/explicit reviewers, both owners and current effect scopes live."""
    _principal(source['owner'])
    _principal(child['owner'])
    ownership = _recorded_owner(connection, child['id'])
    if ownership is not None:
        if (ownership['source_snapshot'] != link['snapshot']
                or actor_identity(ownership['owner']) != actor_identity(child['owner'])
                or actor_identity(ownership['owner']) != actor_identity(source['owner'])):
            raise AgentTaskError('recovery execution ownership does not match the real source')
    _check_pair(ownership or {'owner': source['owner'], 'actor': child['owner']})
    for row in (source, child):
        _task_effect_authority(runtime, connection, row)


def _task_effect_authority(runtime: Any, connection: Any, row: dict) -> None:
    recorded = _recorded_owner(connection, row['id'])
    if recorded is not None and actor_identity(recorded['owner']) != actor_identity(row['owner']):
        raise AgentTaskError('recovery execution task ownership changed')
    check_task_authority(runtime, row['id'])
    with DeferredAuthorization(AuthorizationContext(**row['owner']) if row['owner'] else None).scope():
        pass
    # pylint: disable-next=protected-access  # reason: retain current host profiles and caller origin ceilings
    policy = TaskPolicy(runtime._validated_spec(row['spec']))
    policy.validate_snapshot()
    for action in runtime.store.actions(row['id']):
        if action['status'] == 'confirmed':
            policy.check(action['command'], action['arguments'])


def _check_pair(value: dict) -> None:
    owner, actor = value["owner"], value["actor"]
    with DeferredAuthorization(AuthorizationContext(**actor) if actor else None).scope():
        if not owns_task(owner, current_authorization()):
            raise AuthorizationError("recovery reviewer can no longer manage the source owner's work")
    with DeferredAuthorization(AuthorizationContext(**owner) if owner else None).scope():
        pass
