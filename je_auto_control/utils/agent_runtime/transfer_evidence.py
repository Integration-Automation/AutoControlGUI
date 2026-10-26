"""Source-owned portable grants reuse actual private recovery proof and never export local principals."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import time
from typing import Any, Mapping, Callable
import uuid

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.handoff_records import HandoffAccess, HandoffRecords
from je_auto_control.utils.agent_runtime.transfer_evidence_contract import (
    EVIDENCE_FIELDS, evidence_binding, portable_evidence, request_digest,
)
from je_auto_control.utils.agent_runtime.transfer_host import actor_key, principal
from je_auto_control.utils.agent_runtime.transfer_models import MAX_MANIFEST_BYTES, _canonical, _hex, _object
from je_auto_control.utils.agent_runtime.transfer_records import _text
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint


def _summary(context: dict, identifier: str, source: str, task: str) -> dict:
    proof = context['proof']
    result = {'contract': 1, 'grant_id': identifier, 'source_task': source, 'task_id': task,
        'source_snapshot': context['source_snapshot'], 'completion_snapshot': context['completion_snapshot'],
        'submitted_spec_digest': context['submitted_spec_digest'], 'chain': deepcopy(proof['segments']),
        'verification': context['task']['verification'], 'expires': proof['expires'],
        'evidence_only': True, 'input_authorized': False}
    if context['node'] is not None:
        result['node'] = {name: context['node'][name] for name in ('batch_id', 'graph_hash', 'node_id')}
    return portable_evidence(result, resolved=False)


def _public(record: dict) -> dict:
    state = 'expired' if record['state'] == 'active' and record['expires'] <= time.time() else record['state']
    return {'grant_id': record['id'], 'state': state, 'summary': deepcopy(record['scope']['summary'])}


def _bound_summary(context: dict, record: dict, expected: dict) -> dict:
    if (expected['source_task'] != record['scope']['source_task'] or
            expected['submitted_spec_digest'] != context['submitted_spec_digest'] or
            expected['request_key_hash'] not in {item['key_hash'] for item in context['requests']}):
        raise AgentTaskError('portable evidence does not bind the actual original accepted request')
    node = context['node']
    if (node is None) != ('batch_id' not in expected):
        raise AgentTaskError('portable evidence changed its actual DAG or standalone binding')
    result = deepcopy(record['scope']['summary'])
    if node is not None:
        if any(expected[name] != node[name] for name in ('batch_id', 'graph_hash', 'node_id')):
            raise AgentTaskError('portable evidence belongs to a different actual DAG node')
        result['node']['request_digest'] = request_digest(expected)
    return result


class RemoteEvidenceSource:
    """Explicit consent binds a different private family from local handoffs and artifact exports."""

    def __init__(self, runtime: Any, records: Any, host: Any, checkpoint: Any) -> None:
        self.runtime, self.records, self.host, self.checkpoint = runtime, records, host, checkpoint
        self.reviews: dict[str, dict] = {}
        self.initialized = False

    def _initialize(self) -> None:
        if not self.initialized:
            with self.runtime.store.connection(write=True) as connection:
                self.records.initialize(connection)
            self.initialized = True

    def control(self, operation: str, request: Mapping) -> dict:
        """Review and manage finite source-owned grants without adding foreign task-read authority."""
        self.host.check_open()
        self.checkpoint()
        if not isinstance(operation, str) or operation not in EVIDENCE_FIELDS:
            raise AgentTaskError('portable evidence operation is unavailable')
        value = dict(_object(request, EVIDENCE_FIELDS[operation]))
        actor = principal()
        self._initialize()
        if operation == 'review_evidence':
            return self._review(value, actor)
        if operation == 'create_evidence':
            return self._create(value, actor)
        if operation == 'list_evidence':
            self.host.managed(value['source_task'], actor)
            with self.runtime.store.connection() as connection:
                rows = self.records.entries(connection, 'evidence')
            return {'evidence': [_public(row) for row in rows if row['scope']['source_task'] == value['source_task']]}
        _hex(value['grant_id'], 32)
        with self.runtime.store.connection() as connection:
            row = self.records.find(connection, value['grant_id'])
        self._manager(row, actor)
        if operation == 'revoke_evidence':
            with self.runtime.store.connection(write=True) as connection:
                self._manager(row, principal())
                self.records.revoke(connection, row['id'])
                self.records.release(connection, row['id'])
                row = self.records.find(connection, row['id'])
        return {'evidence': _public(row)}

    def _manager(self, record: dict, actor: dict) -> None:
        if record['kind'] != 'evidence':
            raise AgentTaskError('identity does not select a portable evidence grant')
        self.host.managed(record['scope']['source_task'], actor)

    def _review(self, request: dict, actor: dict) -> dict:
        _text(request['idempotency_key'], 256, 'idempotency key')
        if request['recipient_policy'] not in ('caller', 'source_owner'):
            raise AgentTaskError('evidence recipient must derive caller or original source owner')
        context = self.host.evidence_proof(request['source_task'], request['task_id'], actor, issuing=True)
        identifier, review, now = uuid.uuid4().hex, uuid.uuid4().hex, time.time()
        summary = _summary(context, identifier, request['source_task'], request['task_id'])
        recipient = actor if request['recipient_policy'] == 'caller' else context['owner']
        record = {'id': identifier, 'kind': 'evidence', 'actor': actor_key(actor), 'review': review,
            'key': request['idempotency_key'], 'created': now, 'expires': summary['expires'],
            'review_expires': min(now + 300, summary['expires']), 'size': 0, 'chunks': 0, 'account': None,
            'scope': {'source_task': request['source_task'], 'task_id': request['task_id'], 'issuer': actor,
                      'recipient': recipient, 'recipient_policy': request['recipient_policy'],
                      'context': context, 'summary': summary}}
        if len(_canonical(record)) > MAX_MANIFEST_BYTES:
            raise AgentTaskError('private portable evidence exceeds its bounded record budget')
        self.reviews = {key: value for key, value in self.reviews.items() if value['review_expires'] > now}
        if len(self.reviews) >= 128:
            raise AgentTaskError('pending portable evidence review quota exceeded')
        self.reviews[review] = record
        return {'review': review, 'digest': sha256(_canonical(summary)).hexdigest(), 'evidence': summary,
                'review_expires': record['review_expires'], 'approval_required': True}

    def _check(self, record: dict, *, connection: Any = None, issuing: bool = False,
               checkpoint: Callable | None = None) -> dict:
        check = self.checkpoint if checkpoint is None else checkpoint
        check()
        scope = record['scope']
        current = self.host.evidence_proof(scope['source_task'], scope['task_id'], scope['issuer'],
            connection=connection, reviewed=scope['context']['proof'], issuing=issuing)
        if current != scope['context']:
            raise AgentTaskError('portable evidence or its reviewed private authority changed')
        check()
        return current

    def skill_access(self, connection: Any, source_task: str, task_id: str, grant_id: str) -> HandoffAccess | None:
        """Resolve only this host's selected portable consent inside the existing skill transaction."""
        self.host.check_open()
        cancellation_checkpoint()
        _hex(grant_id, 32)
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='agent_transfer_intents'").fetchone() is None:
            return None
        if connection.execute('SELECT 1 FROM agent_transfer_intents WHERE id=?', (grant_id,)).fetchone() is None:
            return None
        if any(HandoffRecords(kind).find(connection, grant_id) is not None for kind in (False, True)):
            raise AgentTaskError('skill evidence identity has ambiguous private grant families')
        row = self.records.active(connection, grant_id)
        scope = row['scope']
        if (row['kind'] != 'evidence' or scope['source_task'] != source_task or scope['task_id'] != task_id or
                actor_key(principal()) != actor_key(scope['recipient'])):
            raise AgentTaskError('portable skill evidence does not select this source, completion or recipient')
        self._check(row, connection=connection, checkpoint=cancellation_checkpoint)
        access = self.host.skill_evidence(connection, row)
        self.records.active(connection, grant_id)
        self._check(row, connection=connection, checkpoint=cancellation_checkpoint)
        if actor_key(principal()) != actor_key(scope['recipient']):
            raise AgentTaskError('portable skill evidence recipient changed')
        return access

    def _create(self, request: dict, actor: dict) -> dict:
        _hex(request['review'], 32)
        note = _text(request['note'], 4000, 'approval note')
        key = _text(request['idempotency_key'], 256, 'idempotency key')
        with self.runtime.store.connection() as connection:
            previous = self.records.review(connection, request['review'])
        if previous is not None:
            if (previous['kind'] != 'evidence' or previous['actor'] != actor_key(actor) or
                    previous['key_hash'] != key or previous['note_hash'] != note):
                raise AgentTaskError('portable evidence retry changed its actual actor, key or note')
            with self.runtime.store.connection() as connection:
                self.records.active(connection, previous['id'])
            self._check(previous)
            return {'evidence': _public(previous)}
        record = deepcopy(self.reviews.get(request['review']))
        if record is None or record['actor'] != actor_key(actor) or record['key'] != request['idempotency_key']:
            raise AgentTaskError('portable evidence review is unavailable to this actor or key')
        self._check(record, issuing=True)
        with self.runtime.store.connection(write=True) as connection:
            self.records.reserve(connection, record)
            created = self.records.consume_review(connection, record['review'], record['key'], request['note'])
            self._check(created, connection=connection, issuing=True)
        return {'evidence': _public(created)}

    def resolve(self, grant_id: str, binding: Mapping) -> dict:
        """Revalidate one exact original accepted witness under the actual receiving account every time."""
        self.host.check_open()
        self.checkpoint()
        _hex(grant_id, 32)
        expected = evidence_binding(binding)
        actor = principal()
        self._initialize()
        with self.runtime.store.connection() as connection:
            row = self.records.active(connection, grant_id)
        if row['kind'] != 'evidence' or actor_key(actor) != actor_key(row['scope']['recipient']):
            raise AgentTaskError('portable evidence is unavailable to this authenticated recipient')
        context = self._check(row)
        result = _bound_summary(context, row, expected)
        with self.runtime.store.connection() as connection:
            self.records.active(connection, grant_id)
            self._check(row, connection=connection)
            if actor_key(principal()) != actor_key(row['scope']['recipient']):
                raise AgentTaskError('portable evidence recipient changed during resolution')
        return portable_evidence(result)

    def maintain(self) -> None:
        """Expire metadata-only grants independently of artifact byte cleanup and destination receipts."""
        with self.runtime.store.connection() as connection:
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name='agent_transfer_grants'").fetchone() is None:
                return
            rows = [row for row in self.records.entries(connection, 'evidence') if row['expires'] <= time.time()]
        if rows:
            with self.runtime.store.connection(write=True) as connection:
                self.records.prune_kind(connection, 'evidence', time.time())
                for row in rows:
                    if row['held']:
                        self.records.revoke(connection, row['id'])
                        self.records.release(connection, row['id'])

    def close(self) -> None:
        """Discard only unapproved reviews; durable consent and revocations remain with the runtime."""
        self.reviews.clear()


def resolve_remote_evidence(peer: Any, host: str, host_binding: str, grant_id: str,
                            binding: Mapping, timeout: float = 30) -> dict:
    """Resolve fresh authenticated evidence without interpreting foreign principals or local paths."""
    request = {'grant_id': grant_id, 'binding': evidence_binding(binding)}
    return peer.call(host, host_binding, 'evidence', request, timeout)
