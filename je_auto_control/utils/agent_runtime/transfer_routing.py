"""Coordinator-owned routed consent persists exact approval before forwarding source or destination creation."""
from __future__ import annotations

from copy import deepcopy
import time
from typing import Any, Callable, Mapping
import uuid

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_host import actor_key, principal
from je_auto_control.utils.agent_runtime.transfer_evidence_management import evidence_digest
from je_auto_control.utils.agent_runtime.transfer_management import management_request
from je_auto_control.utils.agent_runtime.transfer_models import TransferManifest
from je_auto_control.utils.agent_runtime.transfer_records import TransferRecords, _text


def _created_digest(operation: str, reply: dict) -> str:
    if operation == 'create_evidence':
        return evidence_digest(reply['evidence']['summary'])
    if operation == 'create_import':
        return reply['import']['manifest_digest']
    return TransferManifest.from_dict(reply['export']['manifest']).digest


class RoutedTransfers:
    """A local opaque review binds its actual caller, host fingerprint, foreign review, digest and key."""

    def __init__(self, runtime: Any, records: TransferRecords, peer: Any, binding: Callable,
                 checkpoint: Callable[[], float]) -> None:
        self.runtime, self.records, self.peer = runtime, records, peer
        self.binding, self.checkpoint = binding, checkpoint
        self._reviews: dict[str, dict] = {}
        self._initialized = False

    def control(self, host: str, operation: str, request: Mapping) -> dict:
        """Route only closed source operations; no coordinator path or principal crosses the wire."""
        value = management_request(operation, request)
        if self.peer is None:
            raise AgentTaskError('registered transfer management is unavailable')
        actor, binding = principal(), self.binding(host)
        if operation in {'review_export', 'review_import', 'review_evidence'}:
            return self._review(host, binding, value, actor, operation)
        if operation in {'create_export', 'create_import', 'create_evidence'}:
            return self._create(host, binding, value, actor, operation)
        return self.peer.manage(host, binding, operation, value, self.checkpoint())

    def close(self) -> None:
        """Discard unapproved private reviews while retaining durable approved intents for exact recovery."""
        self._reviews.clear()

    def _check(self, host: str, binding: str) -> None:
        self.checkpoint()
        if self.binding(host) != binding:
            raise AgentTaskError('routed transfer host configuration changed')
        self.checkpoint()

    def _prepare(self, host: str, binding: str) -> None:
        self._check(host, binding)
        with self.runtime.store.connection(write=True) as connection:
            if not self._initialized:
                self.records.initialize(connection)
            self.records.prune_routes(connection)
            self._check(host, binding)
        self._initialized = True

    def _review(self, host: str, binding: str, request: dict, actor: dict, operation: str) -> dict:
        self._prepare(host, binding)
        now = time.time()
        self._reviews = {key: record for key, record in self._reviews.items() if record['review_expires'] > now}
        if len(self._reviews) >= 128:
            raise AgentTaskError('pending routed transfer review quota exceeded')
        reply = self.peer.manage(host, binding, operation, request, self.checkpoint())
        self._check(host, binding)
        now = time.time()
        descriptor = 'evidence' if operation == 'review_evidence' else 'manifest'
        expiry = min(reply[descriptor]['expires'], now + 30 * 86400)
        review_expiry = min(reply['review_expires'], now + 300, expiry)
        review = uuid.uuid4().hex
        self._reviews[review] = {'id': uuid.uuid4().hex, 'kind': 'route', 'actor': actor_key(actor),
            'review': review, 'key': request['idempotency_key'], 'created': now, 'expires': expiry,
            'review_expires': review_expiry, 'size': 0, 'chunks': 0, 'account': None,
            'scope': {'host': host, 'binding': binding, 'peer_review': reply['review'],
                      'digest': reply['digest'], descriptor: deepcopy(reply[descriptor]),
                      'operation': operation.replace('review_', 'create_', 1),
                      'request': deepcopy(request)}}
        return {**reply, 'review': review, 'review_expires': review_expiry}

    def _create(self, host: str, binding: str, request: dict, actor: dict, operation: str) -> dict:
        self._prepare(host, binding)
        record = self._approved(host, binding, request, actor, operation)
        self._check(host, binding)
        forwarded = {**request, 'review': record['scope']['peer_review']}
        reply = self.peer.manage(host, binding, operation, forwarded, self.checkpoint())
        self._check(host, binding)
        digest = _created_digest(operation, reply)
        if digest != record['scope']['digest']:
            raise AgentTaskError('routed creation reply differs from its approved immutable manifest')
        return reply

    def _approved(self, host: str, binding: str, request: dict, actor: dict, operation: str) -> dict:
        key_hash = _text(request['idempotency_key'], 256, 'idempotency key')
        note_hash = _text(request['note'], 4000, 'approval note')
        with self.runtime.store.connection() as connection:
            previous = self.records.review(connection, request['review'])
        pending = self._reviews.get(request['review'])
        if previous is not None:
            record = previous
        elif pending is not None:
            record = deepcopy(pending)
        else:
            raise AgentTaskError('routed transfer review is missing or expired')
        self._bound(record, host, binding, actor, operation)
        if previous is not None:
            if record['key_hash'] != key_hash or record['note_hash'] != note_hash:
                raise AgentTaskError('routed retry changed its original key or approval note')
        elif record['key'] != request['idempotency_key'] or record['review_expires'] <= time.time():
            raise AgentTaskError('routed review key changed or its consent expired')
        with self.runtime.store.connection(write=True) as connection:
            if previous is None:
                self.records.reserve(connection, record)
            created = self.records.consume_review(connection, request['review'],
                                                   request['idempotency_key'], request['note'])
            self._check(host, binding)
        self._reviews.pop(request['review'], None)
        return created

    @staticmethod
    def _bound(record: dict, host: str, binding: str, actor: dict, operation: str) -> None:
        scope = record['scope']
        if (record['kind'] != 'route' or record['actor'] != actor_key(actor)
                or scope.get('host') != host or scope.get('binding') != binding
                or scope.get('operation') != operation):
            raise AgentTaskError('routed review belongs to a different caller, host or operation')
