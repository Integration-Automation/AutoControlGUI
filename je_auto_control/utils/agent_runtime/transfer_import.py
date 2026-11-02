"""Destination-owned consent and fenced recovery bind source manifests to immutable local files profiles."""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
import time
from typing import Any, Callable, Mapping
import uuid

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_host import actor_key, principal, _refresh
from je_auto_control.utils.agent_runtime.transfer_models import TransferManifest, _object, _hex
from je_auto_control.utils.agent_runtime.transfer_records import TransferRecords, _text
from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
from je_auto_control.utils.agent_runtime.transfer_import_files import (
    publish_import, receive_chunks, inspect_import, publication_root, retire_import_staging,
)
from je_auto_control.utils.agent_runtime.transfer_import_jobs import TransferImportJobs
from je_auto_control.utils.agent_runtime.transfer_import_contract import IMPORT_FIELDS


@dataclass
class _ImportState:
    """Unapproved reviews belong only to the current runtime; approved intents will be durable."""

    reviews: dict[str, dict] = field(default_factory=dict)
    enabled: bool = False
    jobs: Any = None


def import_maintenance_pending(store: Any) -> bool:
    """Find expired or cancelled destination work without starting a listener or any delivery producer."""
    with store.connection() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' "
                  "AND name IN ('agent_transfer_imports','agent_transfer_deliveries')")}
        if len(tables) != 2:
            return False
        return connection.execute('SELECT 1 FROM agent_transfer_imports i '
            'JOIN agent_transfer_deliveries d ON d.id=i.id WHERE i.kind=\'import\' '
            "AND (i.expires<=? OR (i.held=1 AND (i.state='revoked' OR d.state IN ('cancelled','expired')))) LIMIT 1",
            (time.time(),)).fetchone() is not None


class TransferImporter:
    """A destination resolves its own registered source and never trusts coordinator-local file bytes."""

    def __init__(self, runtime: Any, records: TransferRecords, host: Any, peer: Any,
                 remaining: Callable[[], float]) -> None:
        self.runtime, self.records, self.host, self.remote = runtime, records, host, peer
        self.remaining = remaining
        self._state = _ImportState()

    def control(self, operation: str, request: Mapping) -> dict:
        """Review only exact destination management envelopes under actual current local authority."""
        value = dict(_object(request, IMPORT_FIELDS[operation]))
        actor = principal()
        if operation == 'review_import':
            return self._review(value, actor)
        if operation == 'create_import':
            return self._create(value, actor)
        jobs = self._jobs()
        with self.runtime.store.connection() as connection:
            if operation == 'list_imports':
                rows = self.records.entries(connection, 'import')
                return {'imports': [self._public(row, connection) for row in rows if row['actor'] == actor_key(actor)]}
            _hex(value['import_id'], 32)
            row = self.records.find(connection, value['import_id'])
            self._owner(row, actor)
        if operation == 'cancel_import':
            with self.runtime.store.connection(write=True) as connection:
                self._owner(row, principal())
                jobs.ledger.cancel(connection, row['id'])
        if operation == 'run_import':
            self._run(row)
        with self.runtime.store.connection() as connection:
            reply = {'import': self._public(row, connection)}
        if operation == 'run_import':
            jobs.wake()
        return reply

    def enable(self) -> None:
        """Enable delivery only after the owning service has explicitly started its listener."""
        self._state.enabled = True
        with self.runtime.store.connection() as connection:
            retained = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                                          "name='agent_transfer_imports'").fetchone()
        if retained is not None:
            self._jobs().start_pending()

    def _jobs(self) -> TransferImportJobs:
        if not self._state.enabled:
            raise AgentTaskError('destination import needs a started runtime service')
        if self._state.jobs is None:
            with self.runtime.store.connection(write=True) as connection:
                self.records.initialize(connection)
            self._state.jobs = TransferImportJobs(self)
        return self._state.jobs

    @staticmethod
    def _owner(row: dict, actor: dict) -> None:
        if row['kind'] != 'import' or row['actor'] != actor_key(actor):
            raise AgentTaskError('destination import belongs to another recipient')

    def _local(self, row: dict, *, connection: Any = None) -> dict:
        with _refresh(row['scope']['issuer']).scope():
            destination = row['scope']['destination']
            current = self.host.destination_context(destination['profile']['name'], destination['directory'],
                                                   reviewed=destination, connection=connection)
        if row['expires'] <= time.time():
            raise AgentTaskError('destination import receipt has expired')
        return current

    def _current(self, row: dict) -> None:
        self._local(row)
        if self.runtime.batches.transfer_binding(row['scope']['source_host']) != row['scope']['binding']:
            raise AgentTaskError('destination source registration changed')

    def _manifest(self, row: dict, timeout: float) -> TransferManifest:
        self._current(row)
        scope = row['scope']
        with _refresh(scope['issuer']).scope():
            manifest = TransferManifest.from_dict(self.remote.call(scope['source_host'], scope['binding'], 'export',
                {'export_id': scope['manifest']['export_id']}, timeout))
        self._current(row)
        if manifest.digest != scope['digest']:
            raise AgentTaskError('source export differs from the reviewed manifest')
        return manifest

    def _create(self, request: dict, actor: dict) -> dict:
        _hex(request['review'], 32)
        note_hash = _text(request['note'], 4000, 'approval note')
        key_hash = _text(request['idempotency_key'], 256, 'idempotency key')
        jobs = self._jobs()
        with self.runtime.store.connection() as connection:
            previous = self.records.review(connection, request['review'])
        row = previous if previous is not None else self._state.reviews.get(request['review'])
        if row is None:
            raise AgentTaskError('destination import review is missing or expired')
        row = deepcopy(row)
        self._owner(row, actor)
        if previous is not None:
            if row['key_hash'] != key_hash or row['note_hash'] != note_hash:
                raise AgentTaskError('destination approval changed its note or key')
        elif row['key'] != request['idempotency_key'] or row['review_expires'] <= time.time():
            raise AgentTaskError('destination review key changed or its approval expired')
        self._manifest(row, self.remaining())
        with self.runtime.store.connection(write=True) as connection:
            self._local(row, connection=connection)
            if previous is None:
                row['scope']['destination'] = self._local(row, connection=connection)
                self.records.reserve(connection, row)
            accepted = self.records.consume_review(
                connection, row['review'], request['idempotency_key'], request['note'])
            if previous is None:
                jobs.ledger.enqueue(connection, row['id'])
            self._local(row, connection=connection)
        self._current(accepted)
        with self.runtime.store.connection() as connection:
            reply = {'import': self._public(accepted, connection)}
        jobs.wake()
        return reply

    def _public(self, row: dict, connection: Any) -> dict:
        delivery = self._state.jobs.ledger.read(connection, row['id'])
        state = delivery['state'] if row['expires'] > time.time() else 'expired'
        return {'import_id': row['id'], 'state': state, 'expires': row['expires'],
                'manifest_digest': row['scope']['digest'],
                'files_directory': delivery['files_directory'] if state == 'published' else None}

    def _run(self, row: dict) -> None:
        jobs = self._state.jobs
        with self.runtime.store.connection() as connection:
            retained = jobs.ledger.read(connection, row['id'])
        self._delivery_scope(row, retained)
        self._manifest(row, self.remaining())
        if retained['publication']:
            publication_root(row, retained['publication'])
        with self.runtime.store.connection(write=True) as connection:
            self.records.active(connection, row['id'])
            destination = self._local(row, connection=connection)
            delivery = jobs.ledger.read(connection, row['id'])
            if delivery['state'] == 'requires_review':
                jobs.ledger.requeue(connection, row['id'], ceilings=destination['origins'])
            elif delivery['state'] != 'queued':
                raise AgentTaskError('destination import is not an unstarted queued delivery')
            else:
                jobs.ledger.pin_ceilings(connection, row['id'], destination['origins'])
            self._local(row, connection=connection)
        self._current(row)

    @staticmethod
    def _delivery_scope(row: dict, delivery: dict) -> None:
        row['scope']['destination']['origins'] = list(dict.fromkeys([
            *row['scope']['destination']['origins'], *delivery['ceilings']]))

    def deliver(self, import_id: str, generation: int, check: Callable[[], None]) -> dict:
        """Receive and independently verify real source bytes under the persisted original local issuer."""
        jobs = self._state.jobs
        with self.runtime.store.connection() as connection:
            row = self.records.active(connection, import_id)
            delivery = jobs.ledger.check(connection, import_id, generation)
        self._delivery_scope(row, delivery)
        deadline = time.monotonic() + 300
        def checkpoint() -> None:
            check()
            self._current(row)
            if time.monotonic() >= deadline:
                raise AgentTaskError('destination import delivery deadline exhausted')
        def budget() -> float:
            checkpoint()
            return min(30, deadline - time.monotonic())
        with _refresh(row['scope']['issuer']).scope():
            manifest = self._manifest(row, budget())
            if not delivery['publication']:
                self._receive(row, manifest, generation, checkpoint, budget)
            self._manifest(row, budget())
            with self.runtime.store.connection() as connection:
                publication = jobs.ledger.check(connection, import_id, generation)['publication']
            result = inspect_import(row, manifest, publication, checkpoint)
            with self.runtime.store.connection(write=True) as connection:
                self._local(row, connection=connection)
                jobs.ledger.advance(connection, import_id, generation, 'published',
                                    files_directory=str(result.directory))
                self._local(row, connection=connection)
            return {'import_id': import_id, 'state': 'published'}

    def _receive(self, row: dict, manifest: TransferManifest, generation: int, checkpoint: Callable,
                 budget: Callable) -> Any:
        jobs = self._state.jobs
        cache = PrivateTransferCache(self.runtime.store.path)
        def read(digest: str) -> dict:
            scope = row['scope']
            return self.remote.call(scope['source_host'], scope['binding'], 'chunk',
                {'export_id': manifest.export_id, 'sha256': digest}, budget())
        receive_chunks(row, manifest, cache, read, checkpoint)
        self._manifest(row, budget())
        with self.runtime.store.connection(write=True) as connection:
            self._local(row, connection=connection)
            jobs.ledger.advance(connection, row['id'], generation, 'verified')
            self._local(row, connection=connection)
        def publication(value: dict) -> None:
            with self.runtime.store.connection(write=True) as connection:
                self._local(row, connection=connection)
                jobs.ledger.advance(connection, row['id'], generation, 'verified', publication=value)
                self._local(row, connection=connection)
        def staging_retired(witness: dict) -> None:
            with self.runtime.store.connection(write=True) as connection:
                jobs.ledger.staging_retired(connection, row['id'], witness)
        return publish_import(row, manifest, cache, checkpoint, publication, staging_retired)

    def delivery_failed(self, import_id: str, generation: int) -> None:
        """Keep failed or unknown publication explicit and retain capacity until producer cleanup is proven."""
        with self.runtime.store.connection(write=True) as connection:
            row = self._state.jobs.ledger.read(connection, import_id)
            if row['generation'] == generation and row['state'] in {'receiving', 'verified'}:
                connection.execute("UPDATE agent_transfer_deliveries SET state='requires_review',"
                                   'generation=generation+1,updated=? WHERE id=? AND generation=?',
                                   (time.time(), import_id, generation))

    def maintain(self) -> None:
        """Retire owned private bytes and expired metadata without extending consent or starting producers."""
        jobs = self._state.jobs
        if jobs is None:
            if not import_maintenance_pending(self.runtime.store):
                return
            jobs = self._state.jobs = TransferImportJobs(self)
        cutoff = time.time()
        with self.runtime.store.connection() as connection:
            prunable = jobs.ledger.prunable(connection, cutoff)
            rows = connection.execute("SELECT id FROM agent_transfer_imports WHERE kind='import' "
                                      'AND held=1 ORDER BY id LIMIT 16').fetchall()
            records = [self.records.find(connection, row['id']) for row in rows]
            pending = [record['id'] for record in records if self._cleanup_candidate(
                record, jobs.ledger.read(connection, record['id']))]
        if prunable:
            with self.runtime.store.connection(write=True) as connection:
                jobs.ledger.prune(connection, cutoff)
        for identifier in pending:
            self._cleanup_account(identifier)

    def _cleanup_candidate(self, record: dict, delivery: dict) -> bool:
        if not record['held']:
            return False
        if record['expires'] <= time.time():
            return True
        return delivery['state'] in {'cancelled', 'expired'} and self._state.jobs.retired(record['id'])

    def _cleanup_account(self, identifier: str) -> None:
        jobs = self._state.jobs
        with self.runtime.store.connection(write=True) as connection:
            record = self.records.find(connection, identifier)
            delivery = jobs.ledger.read(connection, identifier)
            if not self._cleanup_candidate(record, delivery):
                return
            if record['expires'] <= time.time():
                jobs.ledger.expire(connection, identifier)
            if not jobs.retired(identifier):
                return
            self.records.revoke(connection, identifier)
        witness = retire_import_staging(record, delivery['publication'])
        if witness is not None:
            with self.runtime.store.connection(write=True) as connection:
                jobs.ledger.staging_retired(connection, identifier, witness)
        PrivateTransferCache(self.runtime.store.path).delete_account(record['account'])
        with self.runtime.store.connection(write=True) as connection:
            self.records.release(connection, identifier)

    def _review(self, request: dict, actor: dict) -> dict:
        _text(request['idempotency_key'], 256, 'idempotency key')
        destination = self.host.destination_context(request['target'], request['directory'])
        if self.remote is None:
            raise AgentTaskError('registered source transfer is unavailable')
        binding = self.runtime.batches.transfer_binding(request['source_host'])
        manifest = TransferManifest.from_dict(self.remote.call(request['source_host'], binding, 'export',
            {'export_id': request['export_id']}, self.remaining()))
        self.remaining()
        destination = self.host.destination_context(request['target'], request['directory'], reviewed=destination)
        if self.runtime.batches.transfer_binding(request['source_host']) != binding:
            raise AgentTaskError('source host changed during import review')
        principal()
        now = time.time()
        self._state.reviews = {key: item for key, item in self._state.reviews.items() if item['review_expires'] > now}
        if len(self._state.reviews) >= 128:
            raise AgentTaskError('pending destination review quota exceeded')
        identifier, review = uuid.uuid4().hex, uuid.uuid4().hex
        expires = min(manifest.expires, now + 30 * 86400)
        record = {'id': identifier, 'kind': 'import', 'actor': actor_key(actor), 'review': review,
                  'key': request['idempotency_key'], 'created': now, 'expires': expires,
                  'review_expires': min(expires, now + 300), 'size': sum(item.blob.size for item in manifest.files),
                  'chunks': sum(len(item.blob.chunks) for item in manifest.files), 'account': uuid.uuid4().hex,
                  'scope': {'issuer': actor, 'source_host': request['source_host'], 'binding': binding,
                            'manifest': manifest.to_dict(), 'digest': manifest.digest, 'destination': destination}}
        self._state.reviews[review] = record
        return {'review': review, 'review_expires': record['review_expires'], 'manifest': manifest.to_dict(),
                'digest': manifest.digest, 'approval_required': True}

    def close(self) -> None:
        """Discard only unapproved memory; closing a view cannot consume or recreate consent."""
        self._state.reviews.clear()
        self._state.enabled = False
        if self._state.jobs is not None:
            self._state.jobs.close()
