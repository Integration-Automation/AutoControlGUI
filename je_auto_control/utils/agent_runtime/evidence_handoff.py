"""Explicit revocable evidence-only grants preserve ordinary task ownership and input isolation."""
from __future__ import annotations

from dataclasses import asdict
from contextlib import nullcontext
import hashlib
import json
import math
import time
import uuid
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.completion_contract import validate_recorded_completion
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.handoff_records import HandoffRecords, HandoffAccess, HandoffPolicy
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

OPERATIONS = ('review_handoff', 'create_handoff', 'get_handoff', 'list_handoffs', 'revoke_handoff')
_FIELDS = {'review_handoff': {'task_id', 'batch_id', 'node_id'},
           'create_handoff': {'task_id', 'batch_id', 'node_id', 'review', 'note'},
           'get_handoff': {'handoff_id'}, 'list_handoffs': {'batch_id', 'node_id'},
           'revoke_handoff': {'handoff_id'}}
_TERMINAL = frozenset({'succeeded', 'failed', 'cancelled', 'timed_out'})


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _identity(value: dict) -> tuple[Any, Any]:
    return value.get('user_id'), value.get('store_path')


def _principal() -> dict:
    actor = current_authorization()
    return asdict(actor) if actor is not None else {}


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise AgentTaskError('handoff identity must be a bounded string')
    return value


def _manager(actor: dict, owner: dict) -> None:
    try:
        authority = DeferredAuthorization(AuthorizationContext(**actor) if actor else None)
    except (TypeError, ValueError) as error:
        raise AgentTaskError('invalid handoff principal evidence') from error
    with authority.scope():
        current = current_authorization()
        if current is not None and current.role != 'admin' and _identity(asdict(current)) != _identity(owner):
            raise AuthorizationError('handoff issuer can no longer manage the actual evidence owner')


def _expiry(rows: list[dict]) -> float:
    values = [row['updated'] for row in rows if row['state'] in _TERMINAL]
    if not values or any(isinstance(value, bool) or not isinstance(value, (int, float))
                         or not math.isfinite(value) for value in values):
        raise AgentTaskError('invalid handoff evidence retention witness')
    deadline = min(values) + 30 * 86400
    if deadline <= time.time():
        raise AgentTaskError('handoff evidence has expired')
    return deadline


def _retained_tasks(context: dict, tasks: list[dict]) -> list[dict]:
    rows = context.get('retained_rows', []) + tasks
    return list({row['id']: row for row in rows}.values())


def _public(row: dict) -> dict:
    fields = ('id', *(key for key in ('batch_id', 'node_id') if key in row),
              'source_task', 'task_id', 'review', 'state', 'expires')
    result = {key: row[key] for key in fields}
    if result['state'] == 'active' and result['expires'] <= time.time():
        result['state'] = 'expired'
    return {**result, 'evidence_only': True, 'input_authorized': False}


class EvidenceHandoffs:
    """Grant immutable task/DAG completion projections without ambient task-read capability."""

    def __init__(self, runtime: Any, context: Callable, witness: Callable, scope: Callable | None = None,
                 records: HandoffRecords | None = None) -> None:
        self.runtime, self.context, self.witness = runtime, context, witness
        self.scope = scope
        self.records = records if records is not None else HandoffRecords()

    def control(self, operation: str, request: dict) -> dict:
        """Review, issue, inspect or revoke a closed caller-scoped evidence handoff."""
        self._open()
        expected = _FIELDS[operation]
        if self.records.standalone and operation in {'review_handoff', 'create_handoff', 'list_handoffs'}:
            expected = expected - {'batch_id', 'node_id'} | {'source_task'}
        if set(request) != expected:
            raise AgentTaskError('invalid handoff operation fields')
        for key in set(request) - {'note', 'review'}:
            _identifier(request[key])
        try:
            with DeferredAuthorization.capture().scope():
                if operation in {'get_handoff', 'list_handoffs'}:
                    return self._inspect(operation, request)
                if operation == 'revoke_handoff':
                    return self._revoke(request['handoff_id'])
                return self._issue(operation, request)
        except AuthorizationError as error:
            raise AgentTaskError('handoff authority changed; review again') from error
        except AgentTaskError:
            raise
        except (ValueError, TypeError, KeyError) as error:
            raise AgentTaskError('handoff evidence is malformed; review again') from error

    def _open(self) -> None:
        # pylint: disable-next=protected-access  # reason: preserve the runtime's closed-service boundary for every grant operation
        if self.runtime._closed:
            raise AgentTaskError('runtime is closed')

    def describe(self, connection: Any, request: dict, actor: dict, *, issuing: bool = False,
                 issuer_policies: list[str] | None = None, authorization: dict | None = None) -> tuple:
        """Supply current private proof to an owning host; this neither issues nor consumes a local grant."""
        self._open()
        return self._proof(connection, request, actor, issuing=issuing,
                           issuer_policies=issuer_policies, authorization=authorization)

    def _issue(self, operation: str, request: dict) -> dict:
        actor = _principal()
        with self.runtime.store.connection(write=True) as connection:
            proof, _tasks, _context = self._proof(connection, request, actor, issuing=True)
            review = _digest(proof)
            if operation == 'review_handoff':
                return {'handoff_review': review, 'approval_required': True,
                        'evidence': self._projection(proof)}
            note = request['note']
            if not isinstance(note, str) or not note.strip() or len(note) > 4000 or request['review'] != review:
                raise AgentTaskError('handoff review or bounded nonempty note changed')
            previous = self.records.previous(connection, review)
            if previous is not None:
                if previous['note'] != note:
                    raise AgentTaskError('existing handoff review note differs')
                self._active(connection, dict(previous))
                return {'handoff': _public(dict(previous))}
            row = {'id': uuid.uuid4().hex,
                   **{key: request[key] for key in (*self.records.binding_fields, 'task_id')},
                   'source_task': proof['binding']['source_task'], 'review': review, 'details': json.dumps(proof),
                   'note': note, 'state': 'active', 'created': time.time(), 'expires': proof['expires']}
            self._insert(connection, row)
            if self._proof(connection, request, actor, issuing=True)[0] != proof:
                raise AgentTaskError('handoff evidence changed during creation')
            self._active(connection, row)
        return {'handoff': _public(row)}

    @staticmethod
    def _insert(connection: Any, row: dict) -> None:
        HandoffRecords('batch_id' not in row).insert(connection, row)

    def _context(self, request: dict, *, connection: Any = None, issuer_policies: list[str] | None = None) -> dict:
        options = {'identity_only': True} if self.scope is not None else {}
        identifiers = ((request['source_task'],) if self.records.standalone
                       else (request['batch_id'], request['node_id']))
        return self.context(*identifiers, origin_policies=issuer_policies, connection=connection, **options)

    def _proof(self, connection: Any, request: dict, actor: dict, *, issuing: bool = False,
               issuer_policies: list[str] | None = None,
               authorization: dict | None = None) -> tuple[dict, list[dict], dict]:
        context = self._context(request, connection=connection, issuer_policies=issuer_policies)
        allowed = ({'paused', 'waiting_user', 'recovering', 'cancelled', 'timed_out', 'failed', 'succeeded'}
                   if self.records.standalone else
                   {'waiting_review'} if issuing else {'waiting_review', 'approved', 'running'})
        if context['state'] not in allowed:
            raise AgentTaskError('handoff batch is not in a reviewed evidence state')
        _manager(actor, context['binding']['owner'])
        links = self._chain(connection, context['source']['id'], request['task_id'], issuing=issuing)
        if context.get('ancestor_links', 0) + len(links) > 16:
            raise AgentTaskError('handoff exceeds sixteen real recovery links')
        context['links'] = links
        if self.scope is not None:
            context['issuer'] = actor
            context.update(self.scope(connection, context, links, issuer_policies, authorization, issuing=issuing))
        segments, tasks = self._segments(connection, context, links, actor)
        leaf = tasks[-1]
        reply = self._task(connection, leaf, links[-1][2])
        validate_recorded_completion(reply, context['source']['spec'])
        proof = {'contract': 1, 'binding': context['binding'], 'issuer': actor, 'task_id': leaf['id'],
                 'leaf_owner': leaf['owner'], 'segments': segments, 'expires': _expiry(_retained_tasks(context, tasks)),
                 'issuer_policies': (sorted(context['policy'].spec.options.get('origin_policies', []))
                                     if issuer_policies is None else issuer_policies)}
        if context.get('completion_authorization') is not None:
            proof['completion_authorization'] = context['completion_authorization']
        return proof, [self._task(connection, child, link) for _source, child, link in reversed(links)], context

    def _segments(self, connection: Any, context: dict, links: list, actor: dict) -> tuple[list, list]:
        segments, tasks = [], [context['source']]
        for source, child, link in links:
            _manager(actor, source['owner'])
            _manager(actor, child['owner'])
            scoped = context.get('completion_authorization') is not None or context.get('evidence_scope', False)
            options = {'scope': context['policy']} if scoped else {}
            evidence = self.witness(connection, source, child, link, **options)
            for action in evidence['actions']:
                if action['status'] == 'confirmed':
                    context['policy'].check(action['command'], action['arguments'])
            tasks.append(child)
            segments.append({'source_task': source['id'], 'task_id': child['id'],
                             **{key: evidence[key] for key in ('source_snapshot', 'snapshot', 'completion_snapshot')}})
        return segments, tasks

    def _chain(self, connection: Any, root: str, identifier: str, *, issuing: bool) -> list[tuple[dict, dict, dict]]:
        _identifier(identifier)
        chain, seen = [], {root}
        for _index in range(16):
            if identifier in seen:
                break
            seen.add(identifier)
            child = self._row(connection, identifier, issuing=issuing)
            found = connection.execute('SELECT * FROM agent_task_recoveries WHERE task_id=?', (identifier,)).fetchone()
            if found is None:
                break
            link = dict(found)
            source = self._row(connection, link['source_task'], issuing=issuing)
            chain.append((source, child, link))
            if source['id'] == root:
                return list(reversed(chain))
            identifier = source['id']
        raise AgentTaskError('handoff has no bounded real recovery chain to the original DAG source')

    def _row(self, connection: Any, identifier: str, *, issuing: bool) -> dict:
        if issuing:
            # pylint: disable-next=protected-access  # reason: keep ordinary task ownership before reading issuance evidence
            self.runtime._row(identifier)
        row = self.runtime.store.read_task(connection, identifier)
        if issuing:
            _manager(_principal(), row['owner'])
        return row

    def _task(self, connection: Any, row: dict, link: dict) -> dict:
        completion = connection.execute('SELECT contract FROM agent_completion WHERE task_id=?',
                                        (row['id'],)).fetchone()
        return {'task_id': row['id'], 'state': row['state'],
                'verification': [{key: report[key] for key in ('kind', 'status')} for report in row['verification']],
                'metadata': {'completion_contract': completion[0] if completion is not None else 0,
                             'input_released': True, 'recovery': {
                                 'source_task': link['source_task'], 'snapshot': link['snapshot']}}}

    @staticmethod
    def _projection(proof: dict) -> dict:
        binding = proof['binding']
        result = {'contract': 1,
                **{key: binding[key] for key in ('batch_id', 'node_id', 'source_task') if key in binding},
                'task_id': proof['task_id'], 'segments': proof['segments'], 'expires': proof['expires'],
                'evidence_only': True, 'input_authorized': False}
        if 'completion_authorization' in proof:
            bundle = proof['completion_authorization']
            result['completion_authorization'] = {
                'contract': 1, 'completion_task': bundle['completion_task'],
                'completion_review': bundle['completion_review'], 'review': _digest(bundle),
                'approved_root_count': len(bundle['segments'][0]['authorization']['approved_roots']),
                **{name: sorted({origin for segment in bundle['segments']
                                for origin in segment['authorization']['context'][name]})
                   for name in ('replaced_origins', 'retained_origins', 'current_origins')}}
        return result

    def _load(self, connection: Any, identifier: str) -> tuple[dict, dict]:
        _identifier(identifier)
        found = self.records.find(connection, identifier)
        if found is None:
            raise AgentTaskError('handoff does not exist or belongs to another caller')
        row = dict(found)
        try:
            proof = json.loads(row['details'])
            # pylint: disable-next=C0123  # reason: the JSON contract version must be an exact integer, excluding booleans
            valid = (type(proof['contract']) is int and proof['contract'] == 1
                     and all(isinstance(actor, dict) for actor in (
                         proof['issuer'], proof['leaf_owner'], proof['binding']['owner']))
                     and _digest(proof) == row['review']
                     and proof['task_id'] == row['task_id'] and proof['expires'] == row['expires'])
        except (ValueError, TypeError, KeyError) as error:
            raise AgentTaskError('invalid private handoff evidence') from error
        if not valid:
            raise AgentTaskError('private handoff evidence changed')
        return row, proof

    @staticmethod
    def _audit_authority(proof: dict) -> None:
        current = _principal()
        participants = (proof['issuer'], proof['binding']['owner'], proof['leaf_owner'])
        if current and current.get('role') != 'admin' and not any(
                _identity(current) == _identity(actor) for actor in participants):
            raise AgentTaskError('handoff does not exist or belongs to another caller')

    def _inspect(self, operation: str, request: dict) -> dict:
        with self.runtime.store.connection() as connection:
            if operation == 'get_handoff':
                row, proof = self._load(connection, request['handoff_id'])
                self._audit_authority(proof)
                return {'handoff': _public(row)}
            context = self._context(request, connection=connection)
            found = self.records.list(connection, context['binding'])
            return {'handoffs': [_public(dict(row)) for row in found]}

    def _revoke(self, identifier: str) -> dict:
        with self.runtime.store.connection(write=True) as connection:
            row, proof = self._load(connection, identifier)
            self._audit_authority(proof)
            self.records.revoke(connection, identifier, json.dumps(_principal()), time.time())
            with DeferredAuthorization.capture().scope():
                self._audit_authority(proof)
            row['state'] = 'revoked'
        return {'handoff': _public(row)}

    def _active(self, connection: Any, row: dict) -> None:
        current, revoked = self.records.current(connection, row['id'])
        if current is None or current['state'] != 'active' or revoked or row['expires'] <= time.time():
            raise AgentTaskError('handoff is revoked or expired')
        if current['review'] != row['review']:
            raise AgentTaskError('handoff evidence changed')

    def consume(self, batch_id: str, node_id: str, source_task: str, task_id: str, handoff_id: str,
                *, connection: Any = None) -> tuple[dict, list]:
        """Read only completion projections for the exact private grant under the current batch owner."""
        request = {'batch_id': batch_id, 'node_id': node_id, 'source_task': source_task,
                   'task_id': task_id, 'handoff_id': handoff_id}
        projection, tasks, _context = self._consume(request, connection=connection)
        return projection, tasks

    def consume_task(self, source_task: str, task_id: str, handoff_id: str,
                     *, connection: Any = None) -> HandoffAccess:
        """Return a host-only view of precisely the explicitly granted non-DAG completion chain."""
        request = {'source_task': source_task, 'task_id': task_id, 'handoff_id': handoff_id}
        projection, _tasks, context = self._consume(request, connection=connection)
        links = context['links']
        rows = {row['id']: row for pair in links for row in pair[:2]}
        grant = {**projection['metadata']['evidence_handoff'], 'source_task': source_task, 'task_id': task_id}
        authority = HandoffPolicy(context['policy'], context.get('completion_authorization') is not None)
        return HandoffAccess(projection, rows, links, authority, self.witness, grant)

    def _consume(self, request: dict, *, connection: Any = None) -> tuple[dict, list, dict]:
        self._open()
        try:
            transaction = self.runtime.store.connection(write=True) if connection is None else nullcontext(connection)
            with DeferredAuthorization.capture().scope(), transaction as active_connection:
                row, previous = self._load(active_connection, request['handoff_id'])
                self._audit_authority(previous)
                self._active(active_connection, row)
                fields = (*self.records.binding_fields, 'source_task', 'task_id')
                if any(row[key] != request[key] for key in fields):
                    raise AgentTaskError('handoff batch, node, source or evidence identity differs')
                proof, tasks, context = self._proof(active_connection, row, previous['issuer'],
                                           issuer_policies=previous['issuer_policies'],
                                           authorization=previous.get('completion_authorization'))
                if proof != previous or self._proof(active_connection, row, previous['issuer'],
                        issuer_policies=previous['issuer_policies'],
                        authorization=previous.get('completion_authorization'))[0] != previous:
                    raise AgentTaskError('handoff evidence or binding changed')
                self._active(active_connection, row)
                tasks[0]['metadata']['evidence_handoff'] = {
                    'contract': 1, 'id': request['handoff_id'], 'review': row['review']}
                return tasks[0], tasks, context
        except AuthorizationError as error:
            raise AgentTaskError('handoff authority changed; review again') from error
        except AgentTaskError:
            raise
        except (ValueError, TypeError, KeyError) as error:
            raise AgentTaskError('handoff evidence is malformed; review again') from error
