"""Explicitly reviewed source artifacts publish immutable blobs under live host-derived authority."""
from __future__ import annotations

import base64
from copy import deepcopy
import time
from typing import Any, Mapping
import uuid

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
from je_auto_control.utils.agent_runtime.transfer_files import SourceFile, snapshot_file, verify_source_files
from je_auto_control.utils.agent_runtime.transfer_host import actor_key, principal
from je_auto_control.utils.agent_runtime.transfer_models import MAX_TRANSFER_BYTES, TransferManifest, _hex, _object
from je_auto_control.utils.agent_runtime.transfer_records import TransferRecords, _text
from je_auto_control.utils.agent_runtime.transfer_selection import TextCriterion, selected_files

_FIELDS = {'review_export': {'source_task', 'selection', 'recipient_policy', 'idempotency_key'},
           'create_export': {'review', 'note', 'idempotency_key'}, 'get_export': {'export_id'},
           'revoke_export': {'export_id'}, 'list_exports': {'source_task'}}


def _binding(context: dict) -> dict:
    return {key: context[key] for key in ('source_snapshot', 'completion_snapshot', 'submission_digest',
                                         'origin_scope', 'expires')}


def _public(record: dict) -> dict:
    state = record['state']
    if state == 'active' and record['expires'] <= time.time():
        state = 'expired'
    if state == 'reserved':
        state = 'requires_review'
    return {'export_id': record['id'], 'state': state, 'manifest': record['scope']['manifest'],
            'cleanup_pending': state == 'revoked' and record['held']}


class TransferSource:
    """Only an injected host can derive source paths, actual identities and current completion proof."""

    def __init__(self, runtime: Any, records: TransferRecords, host: Any, checkpoint: Any) -> None:
        self.runtime, self.records, self.host = runtime, records, host
        self._reviews: dict[str, dict] = {}
        self._cache = PrivateTransferCache(runtime.store.path)
        self._initialized = False
        self._checkpoint = checkpoint

    def _initialize(self) -> None:
        if not self._initialized:
            with self.runtime.store.connection(write=True) as connection:
                self.records.initialize(connection)
            self._initialized = True

    def control(self, operation: str, request: Mapping[str, Any]) -> dict:
        """Execute only exact local management envelopes; none accept paths or foreign principals."""
        self.host.check_open()
        self._checkpoint()
        actor = principal()
        if not isinstance(operation, str) or operation not in _FIELDS:
            raise AgentTaskError('source transfer operation is unavailable')
        value = dict(_object(request, _FIELDS[operation]))
        self._initialize()
        if operation == 'review_export':
            return self._review(value, actor)
        if operation == 'create_export':
            return self._create(value, actor)
        if operation == 'list_exports':
            self.host.managed(value['source_task'], actor)
            with self.runtime.store.connection() as connection:
                rows = self.records.entries(connection, 'export')
            return {'exports': [_public(row) for row in rows if row['scope']['source_task'] == value['source_task']]}
        with self.runtime.store.connection() as connection:
            row = self.records.find(connection, value['export_id'])
        self._manage(row, actor)
        if operation == 'revoke_export':
            self._cleanup(row)
            with self.runtime.store.connection() as connection:
                row = self.records.find(connection, row['id'])
        return {'export': _public(row)}

    def _manage(self, record: dict, actor: dict) -> None:
        if record['kind'] != 'export':
            raise AgentTaskError('identity is not an export')
        self.host.managed(record['scope']['source_task'], actor)

    def _review(self, request: dict, actor: dict) -> dict:
        _text(request['idempotency_key'], 256, 'idempotency key')
        if request['recipient_policy'] not in ('caller', 'source_owner'):
            raise AgentTaskError('recipient_policy must derive caller or original source owner')
        context = self.host.context(request['source_task'], actor)
        def checkpoint() -> None:
            self._check(context, actor)
        selected = selected_files(context, request['selection'], checkpoint)
        files = self._scan(context, selected, checkpoint)
        identifier, review, account = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
        manifest = TransferManifest(identifier, request['source_task'], context['source_snapshot'],
                                    context['submission_digest'], tuple(item.file for item in files),
                                    context['expires'])
        recipient = actor if request['recipient_policy'] == 'caller' else context['row']['owner']
        now = time.time()
        record = {'id': identifier, 'kind': 'export', 'actor': actor_key(actor), 'review': review,
                  'key': request['idempotency_key'], 'created': now, 'expires': context['expires'],
                  'review_expires': now + 300, 'size': sum(item.file.blob.size for item in files),
                  'chunks': sum(len(item.file.blob.chunks) for item in files), 'account': account,
                  'scope': {'source_task': request['source_task'], 'issuer': actor, 'recipient': recipient,
                            'recipient_policy': request['recipient_policy'], 'binding': _binding(context),
                            'selection': deepcopy(request['selection']),
                            'manifest': manifest.to_dict()}}
        self._reviews = {key: value for key, value in self._reviews.items() if value['record']['review_expires'] > now}
        if len(self._reviews) >= 128:
            raise AgentTaskError('pending export review limit exceeded')
        self._reviews[review] = {'record': record, 'files': files, 'selected': selected}
        return {'review': review, 'digest': manifest.digest, 'manifest': manifest.to_dict(),
                'review_expires': now + 300, 'approval_required': True}

    def _scan(self, context: dict, selected: list, checkpoint: Any, *,
              account: str | None = None) -> tuple[SourceFile, ...]:
        result, remaining = [], MAX_TRANSFER_BYTES
        for path, clause in selected:
            storage = None if account is None else (self._cache.store, account)
            text = TextCriterion(clause['value']) if clause['kind'] == 'file_text' else None
            item = snapshot_file(context['policy'], path, checkpoint, storage=storage, max_bytes=remaining,
                                 inspect=text.feed if text is not None else None)
            self._criterion(item, clause, text)
            result.append(item)
            remaining -= item.file.blob.size
        return tuple(result)

    @staticmethod
    def _criterion(item: SourceFile, clause: dict, text: TextCriterion | None) -> None:
        if clause['kind'] == 'file_sha256' and item.file.blob.sha256 != clause['value']:
            raise AgentTaskError('source bytes no longer satisfy the selected hash criterion')
        if 'expected_size' in clause and item.file.blob.size != clause['expected_size']:
            raise AgentTaskError('source bytes no longer match the selected manifest size')
        if clause['kind'] == 'file_exists' and item.file.blob.size < int(clause.get('min_bytes', 1)):
            raise AgentTaskError('source bytes no longer satisfy the selected minimum size')
        if text is not None:
            text.finish()

    def _check(self, context: dict, issuer: dict, *, connection: Any = None) -> None:
        self._checkpoint()
        self._cache.check()
        current = self.host.context(context['row']['id'], issuer, connection=connection,
                                    origin_scope=context['origin_scope'])
        if _binding(current) != _binding(context):
            raise AgentTaskError('source evidence or reviewed authority changed')
        self._checkpoint()

    def _create(self, request: dict, actor: dict) -> dict:
        _hex(request['review'], 32)
        note_hash = _text(request['note'], 4000, 'approval note')
        key_hash = _text(request['idempotency_key'], 256, 'idempotency key')
        previous = self._retry(request, actor, note_hash, key_hash)
        if previous is not None:
            return {'export': _public(previous)}
        reviewed = self._reviews.get(request['review'])
        if reviewed is None:
            raise AgentTaskError('export review is missing or expired')
        record = deepcopy(reviewed['record'])
        if record['actor'] != actor_key(actor) or record['key'] != request['idempotency_key']:
            raise AgentTaskError('export review belongs to another actor or key')
        if record['review_expires'] <= time.time():
            raise AgentTaskError('export review has expired')
        record['scope']['note_hash'] = note_hash
        context = self.host.context(record['scope']['source_task'], actor,
                                    origin_scope=record['scope']['binding']['origin_scope'])
        if _binding(context) != record['scope']['binding']:
            raise AgentTaskError('export source changed after review')
        selected = selected_files(context, record['scope']['selection'], lambda: self._check(context, actor))
        if selected != reviewed['selected']:
            raise AgentTaskError('source manifest changed after review')
        with self.runtime.store.connection(write=True) as connection:
            self.records.reserve(connection, record)
            self._check(context, actor, connection=connection)
        accepted = False
        try:
            files = self._scan(context, reviewed['selected'], lambda: self._check(context, actor),
                               account=record['account'])
            if files != reviewed['files']:
                raise AgentTaskError('export file identity or contents changed after review')
            with self.runtime.store.connection(write=True) as connection:
                self._check(context, actor, connection=connection)
                verify_source_files(context['policy'], files, self._checkpoint)
                created = self.records.consume_review(connection, record['review'], record['key'], request['note'])
                verify_source_files(context['policy'], files, self._checkpoint)
                self._check(context, actor, connection=connection)
            accepted = True
            return {'export': _public(created)}
        finally:
            if not accepted:
                self._cleanup(record)

    def _retry(self, request: dict, actor: dict, note_hash: str, key_hash: str) -> dict | None:
        with self.runtime.store.connection() as connection:
            previous = self.records.review(connection, request['review'])
        if previous is None:
            return None
        if (previous['kind'] != 'export' or previous['actor'] != actor_key(actor)
                or previous['key_hash'] != key_hash or previous['scope']['note_hash'] != note_hash):
            raise AgentTaskError('export retry does not match its original consent')
        self._live(previous)
        return previous

    def _live(self, record: dict) -> dict:
        self._checkpoint()
        with self.runtime.store.connection() as connection:
            active = self.records.active(connection, record['id'])
        scope = active['scope']
        current = self.host.context(scope['source_task'], scope['issuer'],
                                    origin_scope=scope['binding']['origin_scope'])
        if _binding(current) != scope['binding']:
            raise AgentTaskError('source export evidence or scope changed')
        self._cache.check()
        return current

    def peer(self, operation: str, request: Mapping[str, Any]) -> dict:
        """Read only exact committed manifests or selected content hashes as their actual local recipient."""
        fields = {'export_id'} if operation == 'export' else {'export_id', 'sha256'}
        if not isinstance(operation, str) or operation not in {'export', 'chunk'}:
            raise AgentTaskError('peer export operation is unavailable')
        value = _object(request, fields)
        actor = principal()
        self._initialize()
        with self.runtime.store.connection() as connection:
            row = self.records.find(connection, value['export_id'])
        if row['kind'] != 'export' or actor_key(actor) != actor_key(row['scope']['recipient']):
            raise AgentTaskError('export is unavailable to this authenticated recipient')
        self._live(row)
        manifest = TransferManifest.from_dict(row['scope']['manifest'])
        if operation == 'export':
            return manifest.to_dict()
        _hex(value['sha256'], 64)
        selected = {digest for item in manifest.files for digest in item.blob.chunks}
        if value['sha256'] not in selected:
            raise AgentTaskError('chunk is outside this exact export manifest')
        body = self._cache.store.read_chunk(row['account'], value['sha256'])
        self._live(row)
        return {'contract': 1, 'sha256': value['sha256'], 'data': base64.b64encode(body).decode('ascii')}

    def _cleanup(self, record: dict) -> None:
        with self.runtime.store.connection(write=True) as connection:
            self.records.revoke(connection, record['id'])
        self._cache.delete_account(record['account'])
        with self.runtime.store.connection(write=True) as connection:
            self.records.release(connection, record['id'])
