"""Host-injected source authority keeps policy and private completion validators out of transfer leaves."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict
from hashlib import sha256
import time
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.completion_contract import validate_recorded_completion
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import _canonical, _deadline, _hex
from je_auto_control.utils.rbac.authorization import AuthorizationContext, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization


def principal() -> dict:
    """Capture only the actual local authenticated identity, never a request-authored principal."""
    with DeferredAuthorization.capture().scope():
        current = current_authorization()
        return asdict(current) if current is not None else {}


def actor_key(actor: dict) -> str:
    """Bind stable principal provenance while checking current roles separately on each operation."""
    return sha256(_canonical({'user_id': actor.get('user_id'), 'store_path': actor.get('store_path')})).hexdigest()


def _refresh(actor: dict) -> DeferredAuthorization:
    return DeferredAuthorization(AuthorizationContext(**actor) if actor else None)


def _manager(actor: dict, owner: dict) -> None:
    with _refresh(actor).scope():
        current = current_authorization()
        if current is not None and current.role != 'admin' and actor_key(asdict(current)) != actor_key(owner):
            raise AgentTaskError('source task does not exist or belongs to another caller')


def _with_origin_scope(spec: dict, scope: list[str] | None) -> dict:
    if scope is None:
        return spec
    options = spec['options']
    origins = list(dict.fromkeys([*options.get('origin_policies', ()), *scope]))
    if not origins and 'origin_policies' not in options:
        return spec
    return {**spec, 'options': {**options, 'origin_policies': origins}}


class TransferHost:
    """Actual runtime callbacks supply policy, private completion checks and lifecycle observations."""

    def __init__(self, runtime: Any, policy: tuple[Callable, Callable], completion: Callable,
                 available: Callable[[], bool], retired: Callable[[str], bool]) -> None:
        self.runtime, self.completion = runtime, completion
        self.policy, self.submitted = policy
        self.available, self.retired = available, retired

    def managed(self, source_task: str, actor: dict, *, connection: Any = None) -> dict:
        """Authorize source management without requiring still-active export or input authority."""
        self.check_open()
        _hex(source_task, 32)
        transaction = self.runtime.store.connection() if connection is None else nullcontext(connection)
        with transaction as reading:
            row = self.runtime.store.read_task(reading, source_task)
            _manager(actor, row['owner'])
            return row

    def context(self, source_task: str, issuer: dict, *, connection: Any = None,
                origin_scope: list[str] | None = None) -> dict:
        """Recheck actual completion and current source/issuer rights without exporting private evidence."""
        self.check_open()
        transaction = self.runtime.store.connection() if connection is None else nullcontext(connection)
        with transaction as reading:
            row = self.managed(source_task, issuer, connection=reading)
            with _refresh(row['owner']).scope():
                pass
            with _refresh(issuer).scope():
                policy = self.policy(_with_origin_scope(row['spec'], origin_scope))
                self.runtime.target_profiles.check(policy.spec)
                self.completion(self.runtime, source_task, connection=reading)
                marker = reading.execute('SELECT contract FROM agent_completion WHERE task_id=?',
                                         (source_task,)).fetchone()
                released = self.retired(source_task) and not reading.execute(
                    'SELECT 1 FROM agent_control WHERE owner=?', (source_task,)).fetchone()
                validate_recorded_completion({'state': row['state'], 'verification': row['verification'],
                    'metadata': {'completion_contract': marker[0] if marker else 0, 'input_released': released}},
                    row['spec'])
                snapshot = self.runtime.recovery.handoff_snapshot(reading, row)
            accepted = reading.execute('SELECT spec_digest FROM agent_task_submissions WHERE task_id=?',
                                       (source_task,)).fetchone()
        _deadline(row['updated'])
        expires = row['updated'] + 30 * 86400
        if row['updated'] > time.time() or expires <= time.time():
            raise AgentTaskError('source evidence retention is expired or invalid')
        return {'row': row, 'policy': policy,
                'origin_scope': list(policy.spec.options.get('origin_policies', ())),
                'source_snapshot': snapshot['snapshot'], 'completion_snapshot': snapshot['completion_snapshot'],
                'submission_digest': accepted[0] if accepted else self.submitted(row['spec']), 'expires': expires}

    def check_open(self) -> None:
        """Fail before opening stores after the owning runtime has closed."""
        if not self.available():
            raise AgentTaskError('runtime is closed')
