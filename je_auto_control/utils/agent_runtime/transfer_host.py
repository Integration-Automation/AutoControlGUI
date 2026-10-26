"""Host-injected source authority and destination scope keep task policy out of transfer leaves."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import time
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.completion_contract import validate_recorded_completion
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.evidence_handoff import EvidenceHandoffs
from je_auto_control.utils.agent_runtime.handoff_records import HandoffRecords, HandoffAccess, HandoffPolicy
from je_auto_control.utils.agent_runtime.transfer_models import _canonical, _deadline, _hex
from je_auto_control.utils.agent_runtime.transfer_privacy import SourceFilePolicy
from je_auto_control.utils.agent_runtime.transfer_lineage import SourceLineage
from je_auto_control.utils.agent_runtime.transfer_destination_scope import destination_scope
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

    def __init__(self, runtime: Any, policy: tuple[Callable, ...],
                 completion: Callable, available: Callable[[], bool], retired: Callable[[str], bool]) -> None:
        self.runtime, self.completion = runtime, completion
        self._callbacks = policy
        _policy, submitted, digest, ownership, _paths = policy[:5]
        self.lineage = SourceLineage(runtime, digest, submitted, _manager, retired, ownership)
        self.available, self.retired = available, retired

    @property
    def policy(self) -> Callable:
        """Use the injected source policy factory without a reverse dependency on task models."""
        return self._callbacks[0]

    @property
    def private_paths(self) -> Callable:
        """Inspect actual host-private paths through the source host's existing collaborator."""
        return self._callbacks[4]

    def destination_context(self, target: str, directory: str, *, reviewed: dict | None = None,
                            connection: Any = None) -> dict:
        """Validate a destination against actual local profile and retained live origin constraints."""
        self.check_open()
        return destination_scope(self._callbacks[5], self._callbacks[6], target, directory,
                                 reviewed=reviewed, connection=connection)

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
                lineage = self.lineage.context(reading, row, issuer, origin_scope)
        _deadline(row['updated'])
        expires = row['updated'] + 30 * 86400
        if row['updated'] > time.time() or expires <= time.time():
            raise AgentTaskError('source evidence retention is expired or invalid')
        return {'row': row, 'policy': SourceFilePolicy(policy, self.runtime, (*lineage['owners'], issuer),
                                                       lineage['policies']),
                'origin_scope': list(policy.spec.options.get('origin_policies', ())),
                'source_snapshot': snapshot['snapshot'], 'completion_snapshot': snapshot['completion_snapshot'],
                'submission_digest': lineage['submission_digest'], 'lineage_digest': lineage['digest'],
                'expires': expires}

    def check_open(self) -> None:
        """Fail before opening stores after the owning runtime has closed."""
        if not self.available():
            raise AgentTaskError('runtime is closed')
        for path in self.private_paths():
            private = Path(path).expanduser().resolve()
            if private not in self.runtime.source_private_files:
                self.runtime.source_private_files += (private,)

    def evidence_proof(self, source_task: str, task_id: str, issuer: dict, *, connection: Any = None,
                       reviewed: dict | None = None, issuing: bool = False) -> dict:
        """Reuse actual recovery/completion authority while keeping all private proof on its source host."""
        self.check_open()
        _hex(source_task, 32)
        _hex(task_id, 32)
        previous = {} if reviewed is None else reviewed
        transaction = self.runtime.store.connection() if connection is None else nullcontext(connection)
        with transaction as reading, _refresh(issuer).scope():
            row = self.managed(source_task, issuer, connection=reading)
            engine, request = self._evidence_engine(reading, row, issuer, previous.get('issuer_policies'))
            request['task_id'] = task_id
            described = engine.describe(reading, request, issuer, issuing=issuing,
                issuer_policies=previous.get('issuer_policies'), authorization=previous.get('completion_authorization'))
            return self._evidence_projection(reading, row, task_id, *described[:2])

    def _evidence_engine(self, connection: Any, row: dict, issuer: dict, origins: list | None) -> tuple:
        context = self.lineage.evidence_context(connection, row, issuer, origins)
        local = 'admission' in context['binding']
        engine = EvidenceHandoffs(self.runtime, lambda *_args, **_kwargs: context,
            self.runtime.recovery.handoff_witness, self._handoff_scope, HandoffRecords(not local))
        request = {'source_task': row['id']}
        if local:
            request.update({name: context['binding'][name] for name in ('batch_id', 'node_id')})
        return engine, request

    def _handoff_scope(self, connection: Any, context: dict, links: list, issuer_policies: list | None,
                       authorization: dict | None, *, issuing: bool = False) -> dict:
        """Revalidate this host's retained private consent while the engine still checks issuance state."""
        return self.runtime.recovery.handoff_scope(connection, context, links, issuer_policies, authorization,
            issuing=issuing and authorization is None)

    def _evidence_projection(self, connection: Any, row: dict, task_id: str, proof: dict, tasks: list) -> dict:
        requests = self.lineage.accepted_requests(connection, row)
        if not requests:
            raise AgentTaskError('portable evidence requires an actual original accepted request witness')
        snapshot = self.runtime.recovery.handoff_snapshot(connection, row)
        leaf = self.runtime.store.read_task(connection, task_id)
        completion = self.runtime.recovery.handoff_snapshot(connection, leaf)
        submitted = connection.execute('SELECT spec_digest FROM agent_task_submissions WHERE task_id=?',
                                       (row['id'],)).fetchone()
        return {'proof': proof, 'task': tasks[0], 'requests': requests, 'owner': row['owner'],
                'source_snapshot': snapshot['snapshot'], 'completion_snapshot': completion['completion_snapshot'],
                'submitted_spec_digest': submitted[0] if submitted else self.lineage.submitted(row['spec']),
                'node': row['spec']['options'].get('dag_batch')}

    def skill_evidence(self, connection: Any, record: dict) -> HandoffAccess:
        """Build a source-private skill view from current portable consent without creating a local grant."""
        scope = record['scope']
        previous = scope['context']['proof']
        with _refresh(scope['issuer']).scope():
            row = self.managed(scope['source_task'], scope['issuer'], connection=connection)
            engine, request = self._evidence_engine(connection, row, scope['issuer'], previous['issuer_policies'])
            request['task_id'] = scope['task_id']
            proof, tasks, context = engine.describe(connection, request, scope['issuer'],
                issuer_policies=previous['issuer_policies'], authorization=previous.get('completion_authorization'))
        if proof != previous:
            raise AgentTaskError('portable skill evidence changed its private recovery proof')
        grant = {'contract': 1, 'id': record['id'], 'review': sha256(_canonical(scope['summary'])).hexdigest(),
                 'source_task': scope['source_task'], 'task_id': scope['task_id']}
        projection = {**tasks[0], 'metadata': {**tasks[0]['metadata'], 'evidence_handoff': grant}}
        links = context['links']
        rows = {item['id']: item for pair in links for item in pair[:2]}
        return HandoffAccess(projection, rows, links,
            HandoffPolicy(context['policy'], context.get('completion_authorization') is not None),
            self.runtime.recovery.handoff_witness, grant)
