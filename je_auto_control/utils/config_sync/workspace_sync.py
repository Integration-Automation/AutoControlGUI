"""Coordinate seven inert definition profiles with durable causal outboxes, recovery baselines and bounded HTTP."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from pathlib import Path
import os
import time
from typing import TYPE_CHECKING, Callable, Iterable, Iterator, Mapping, Optional, cast

from je_auto_control.utils.config_sync.adapter_factory import adapter_from_profile
from je_auto_control.utils.config_sync.adapter_profiles import materialize_sync_profile
from je_auto_control.utils.config_sync.adapter_schema import AdapterKind
from je_auto_control.utils.config_sync.adapters import _DomainAdapter
from je_auto_control.utils.config_sync.asset_commands import _checkpoint, _root
from je_auto_control.utils.config_sync.asset_models import AssetSyncResult
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.config_sync.control_models import (
    ControlKind, SyncControlOperation, SyncControlRequest, SyncControlResult,
)
from je_auto_control.utils.config_sync.http_commands import _retry_policy
from je_auto_control.utils.config_sync.outbox import SyncOutbox
from je_auto_control.utils.config_sync.outbox_models import SyncLocalIdentity, SyncOperation
from je_auto_control.utils.config_sync.peers import FullResyncRequired
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.config_sync.workspace_config import parse_workspace, profile_binding, source_configuration
from je_auto_control.utils.config_sync.workspace_models import (
    SyncWorkspaceError, WorkspaceSyncResult, WorkspaceState, validate_workspace_snapshot,
)
from je_auto_control.utils.config_sync.workspace_store import WorkspaceStore
from je_auto_control.utils.config_sync.workspace_transport import WorkspaceClient, network_options
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
from je_auto_control.utils.path_guard import PathPolicy

if TYPE_CHECKING:
    from sqlite3 import Connection


class SyncWorkspace:
    """Capture, deliver and review explicitly selected sources; received data never changes an active workspace."""

    def __init__(self, configuration: dict[str, object], *, path_policy: Optional[PathPolicy] = None,
                   cancelled: Optional[Callable[[], bool]] = None, clock: Callable[[], float] = time.time) -> None:
        _checkpoint((), path_policy, cancelled)
        self._spec = parse_workspace(configuration, path_policy, cancelled)
        self._policy = path_policy
        self._cancelled = cancelled
        self._owner: ContextVar[str | None] = ContextVar('sync_workspace_owner', default=None)
        self._queue = SyncOutbox(self._spec.outbox_path, clock=clock)
        # pylint: disable-next=protected-access  # reason: workspace control baselines must share the outbox's atomic transaction owner
        self._store = WorkspaceStore(self._queue._database, (self._spec.endpoint, self._spec.user_id), clock)

    def _check(self) -> None:
        _checkpoint(self._spec.roots, self._policy, self._cancelled)
        owner = self._owner.get()
        if owner is not None:
            self._store.check(owner)

    def _poll(self) -> bool:
        self._check()
        return False

    def _renew(self, seconds: float) -> None:
        self._check()
        owner = self._owner.get()
        if owner is None:
            raise SyncWorkspaceError('workspace operation has no owned lease', code='lease_lost')
        self._store.renew(owner, seconds)

    @contextmanager
    def _operation(self, seconds: float = 300) -> Iterator[None]:
        self._check()
        bindings = {cast(str, profile['kind']): profile_binding(profile) for profile in self._spec.profiles}
        owner = self._store.claim(bindings, seconds)
        token = self._owner.set(owner)
        try:
            with secret_log_scope():
                yield
        except SyncWorkspaceError as error:
            self._store.note_error(owner, error.code)
            raise
        finally:
            self._store.release(owner)
            self._owner.reset(token)

    def _identity(self) -> SyncLocalIdentity:
        return self._queue.identity(self._spec.endpoint, self._spec.user_id)

    def _adapters(self, identity: SyncLocalIdentity) -> dict[AdapterKind, _DomainAdapter]:
        result = {}
        for profile in self._spec.profiles:
            adapter = adapter_from_profile(dict(profile, schema_version=1, identity=asdict(identity)),
                                           path_policy=self._policy, cancelled=self._poll)
            result[adapter.kind] = cast(_DomainAdapter, adapter)
        return result

    def _snapshot(self) -> CausalBucket | None:
        return self._queue.snapshot(endpoint=self._spec.endpoint, user_id=self._spec.user_id)

    def _reconcile(self) -> tuple[SyncLocalIdentity, dict[AdapterKind, _DomainAdapter]]:
        identity = self._identity()
        adapters = self._adapters(identity)
        snapshot = self._snapshot()
        if snapshot is not None:
            self._receive_cache(snapshot, adapters)
        committed = set(snapshot.committed) if snapshot is not None else set()
        pending = self._store.pending_entries()
        for kind, adapter in adapters.items():
            entries = {entry.change_id: entry for entry in pending
                       if entry.section == kind and entry.change_id not in committed}
            if entries:
                adapter.receive_entries(entries)
        return identity, adapters

    def _receive_cache(self, snapshot: CausalBucket, adapters: Mapping[AdapterKind, _DomainAdapter]) -> None:
        validate_workspace_snapshot(snapshot)
        reset = self._store.latest_reset()
        for profile in self._spec.profiles:
            kind = cast(AdapterKind, profile['kind'])
            adapter = adapters[kind]
            if reset is not None and adapter.adopted_control() != reset[0].operation_id:
                baseline = self._store.baseline(reset[0].operation_id, kind, source_configuration(profile))
                adapter.adopt_frontier(snapshot, baseline, operation_id=reset[0].operation_id)
            adapter.receive_frontier(snapshot)

    def capture(self) -> int:
        """Queue all current portable local heads once without reading credentials or contacting a server."""
        with self._operation():
            self._pending_reset_guard()
            identity, adapters = self._reconcile()
            return self._capture(identity, adapters)

    def _capture(self, identity: SyncLocalIdentity, adapters: Mapping[AdapterKind, _DomainAdapter]) -> int:
        snapshot = self._snapshot()
        if snapshot is not None:
            snapshot.peers.require_active(identity.origin, epoch=identity.epoch)
        committed = set(snapshot.committed) if snapshot is not None else set()
        local: list[SyncEntry] = []
        for adapter in adapters.values():
            self._renew(300)
            local.extend(entry for entry in adapter.snapshot().values()
                         if entry.origin == identity.origin and entry.change_id not in committed)
        local.sort(key=lambda entry: (entry.section, entry.entry_id, entry.version[identity.origin], entry.change_id))
        operations = (SyncOperation('workspace-' + entry.change_id, identity.endpoint, identity.user_id,
                                    identity.origin, (entry,), identity.epoch) for entry in local)
        self._check()
        return self._queue.enqueue_many(operations)

    def review(self, kind: AdapterKind) -> dict[str, SyncEntry]:
        """Read exact current heads for one selected domain without network, credentials or source observation."""
        self._check()
        identity = self._identity()
        adapters = self._adapters(identity)
        if kind not in adapters:
            raise ConfigSyncError('workspace does not select that profile kind')
        return adapters[kind].review()

    def resolve(self, kind: AdapterKind, entry_id: str, value: dict[str, object], *, observed: Iterable[str],
                  is_deleted: bool = False) -> SyncEntry:
        """Choose a reviewed value/deletion and queue it durably without sending or activating it."""
        with self._operation():
            self._pending_reset_guard()
            identity, adapters = self._reconcile()
            if kind not in adapters:
                raise ConfigSyncError('workspace does not select that profile kind')
            entry = adapters[kind].resolve(entry_id, value, observed=observed, is_deleted=is_deleted)
            self._queue.enqueue(SyncOperation('workspace-' + entry.change_id, identity.endpoint, identity.user_id,
                                              identity.origin, (entry,), identity.epoch))
            return entry

    def materialize(self, target_root: str | Path) -> AssetSyncResult:
        """Publish only a complete ready inert generation; a pending full reset cannot publish retired definitions."""
        with self._operation():
            self._pending_reset_guard()
            target = _root(str(target_root), self._policy)
            identity, adapters = self._reconcile()
            snapshot = self._snapshot()
            if snapshot is not None:
                snapshot.peers.require_active(identity.origin, epoch=identity.epoch)
            return materialize_sync_profile(adapters.values(), target,
                cancelled=lambda: _checkpoint((target,), self._policy, self._poll))

    def _pending_reset_guard(self) -> None:
        operation = self._store.pending_control()
        if operation is not None and operation.kind == 'full_resync':
            raise FullResyncRequired('workspace full resync must finish before new edits or publication')

    def _note(self, code: str) -> None:
        owner = self._owner.get()
        if owner is not None:
            self._store.note_error(owner, code)

    def _client(self, options: dict[str, object]) -> WorkspaceClient:
        seconds = max(300.0, float(cast(float, options.get('timeout_s', 5.0))) * 2 + 5)
        return WorkspaceClient(self._spec, options, lambda: self._renew(seconds))

    @staticmethod
    def _prime_credentials(options: dict[str, object]) -> None:
        environment = options.get('secret_env')
        if isinstance(environment, str):
            remember_secret(os.environ.get(environment, ''))

    def _prepare_reset(self, connection: Connection, operation: SyncControlOperation) -> None:
        adapters = self._adapters(operation.identity)
        for profile in self._spec.profiles:
            kind = cast(AdapterKind, profile['kind'])
            baseline = adapters[kind].source_fingerprints()
            self._store.save_baseline(connection, operation, kind, source_configuration(profile), baseline)

    def _require_reset_baselines(self, operation: SyncControlOperation) -> None:
        for profile in self._spec.profiles:
            self._store.baseline(operation.operation_id, cast(str, profile['kind']), source_configuration(profile))

    def control(self, request: SyncControlRequest | ControlKind, *,
                  options: Optional[dict[str, object]] = None) -> SyncControlResult:
        """Run explicit peer controls; full reset captures source baselines atomically with its durable intent."""
        settings = network_options(options)
        selected = request if isinstance(request, SyncControlRequest) else SyncControlRequest(request)
        with self._operation(max(300.0, float(cast(float, settings.get('timeout_s', 5.0))) * 2 + 5)):
            self._prime_credentials(settings)
            return self._control(selected, settings)

    def _control(self, request: SyncControlRequest, options: dict[str, object]) -> SyncControlResult:
        identity = self._identity()
        # pylint: disable-next=protected-access  # reason: prepare source fingerprints in the same transaction as the durable control barrier
        controls = self._queue._controls()
        operation = controls.enqueue(identity, request.kind, peer_id=request.peer_id,
            discard_pending=request.discard_pending, operation_id=request.operation_id,
            prepare=self._prepare_reset if request.kind == 'full_resync' else None)
        if operation.kind == 'full_resync' and controls.receipt(
                (identity.endpoint, identity.user_id), operation.operation_id) is None:
            self._require_reset_baselines(operation)
        exact = SyncControlRequest(operation.kind, operation.operation_id, operation.peer_id, operation.discard_pending)
        report = self._client(options).control(self._queue, exact, policy=_retry_policy(options.get('policy')),
                                               cancelled=self._poll)
        if not report.pending:
            self._reconcile()
            self._note('')
        return report

    def synchronize(self, *, options: Optional[dict[str, object]] = None) -> WorkspaceSyncResult:
        """Capture offline edits, resume exact requests and reconcile validated receipts without activating sources."""
        settings = network_options(options)
        seconds = max(300.0, float(cast(float, settings.get('timeout_s', 5.0))) * 2 + 5)
        with self._operation(seconds):
            self._prime_credentials(settings)
            operation = self._store.pending_control()
            if operation is not None and operation.kind == 'full_resync':
                if self._resume_control(operation, settings).pending:
                    return self._result(0, 0)
            try:
                identity, adapters = self._reconcile()
                captured = self._capture(identity, adapters)
            except FullResyncRequired:
                self._note('requires_full_resync')
                return self._result(0, 0)
            if not self._connect(settings):
                return self._result(captured, 0)
            client = self._client(settings)
            policy = _retry_policy(settings.get('policy'))
            # pylint: disable-next=protected-access  # reason: workspace metadata controls require baseline preparation and cannot be auto-drained here
            report = self._queue.flush(lambda item: client._deliver(self._queue, item,
                cast(int, settings.get('max_rebases', 3)), self._poll),
                endpoint=self._spec.endpoint, user_id=self._spec.user_id, policy=policy, cancelled=self._poll)
            self._check()
            self._reconcile()
            if not report.failed and self._store.pending_control() is None and not self._has_prepared():
                self._pull(client)
            return self._result(captured, report.delivered)

    def _resume_control(self, operation: SyncControlOperation, options: dict[str, object]) -> SyncControlResult:
        if operation.kind == 'full_resync':
            self._require_reset_baselines(operation)
        request = SyncControlRequest(operation.kind, operation.operation_id, operation.peer_id,
                                     operation.discard_pending)
        return self._control(request, options)

    def _connect(self, options: dict[str, object]) -> bool:
        operation = self._store.pending_control()
        if operation is not None:
            return not self._resume_control(operation, options).pending
        if self._snapshot() is None and not self._has_prepared():
            return not self._control(SyncControlRequest('register'), options).pending
        return True

    def _has_prepared(self) -> bool:
        return any(item.prepared is not None for item in self._queue.pending(
            endpoint=self._spec.endpoint, user_id=self._spec.user_id))

    def _pull(self, client: WorkspaceClient) -> None:
        previous = self._snapshot()
        try:
            snapshot = client.fetch()
            current = self._queue.observe(snapshot, endpoint=self._spec.endpoint,
                                           minimum_revision=previous.revision if previous is not None else 0)
        except FullResyncRequired:
            self._note('requires_full_resync')
            return
        except (OSError, ConfigSyncError) as error:
            raise_caused_run_interruption(error)
            self._note('network_error')
            return
        validate_workspace_snapshot(current)
        self._reconcile()
        self._note('')

    def status(self) -> dict[str, object]:
        """Inspect local metadata and profiles without a source file, network request or credential lookup."""
        self._check()
        outbox = self._queue.status(endpoint=self._spec.endpoint, user_id=self._spec.user_id)
        control = self._queue.control_status(endpoint=self._spec.endpoint, user_id=self._spec.user_id)
        coordination = self._store.info()
        snapshot = self._snapshot()
        identity = None
        conflicts: list[tuple[str, str]] = []
        unresolved: list[tuple[str, str]] = []
        if outbox['origin'] is not None:
            identity = SyncLocalIdentity(self._spec.endpoint, self._spec.user_id, cast(str, outbox['origin']),
                                         cast(int, outbox['epoch']), cast(int, outbox['confirmed_revision']))
            for kind, adapter in self._adapters(identity).items():
                report = adapter.report()
                conflicts.extend((kind, name) for name in report.conflicts)
                unresolved.extend((kind, name) for name in report.unresolved)
            if snapshot is not None:
                _cached_state(snapshot, identity, coordination)
        pending = cast(int, outbox['pending']) + cast(int, control['pending'])
        return {'identity': asdict(identity) if identity is not None else None,
                'outbox': outbox, 'control': control, 'coordination': coordination,
                'revision': snapshot.revision if snapshot is not None else 0,
                'conflicts': tuple(sorted(conflicts)), 'unresolved': tuple(sorted(unresolved)),
                'state': _workspace_state(outbox, control, coordination, conflicts, unresolved, pending)}

    def _result(self, captured: int, delivered: int) -> WorkspaceSyncResult:
        status = self.status()
        outbox, control = cast(dict[str, object], status['outbox']), cast(dict[str, object], status['control'])
        return WorkspaceSyncResult(captured, delivered, cast(int, outbox['pending']) + cast(int, control['pending']),
            cast(int, status['revision']), cast(tuple[tuple[str, str], ...], status['conflicts']),
            cast(tuple[tuple[str, str], ...], status['unresolved']), cast(WorkspaceState, status['state']))


def _cached_state(snapshot: CausalBucket, identity: SyncLocalIdentity, metadata: dict[str, object]) -> None:
    try:
        validate_workspace_snapshot(snapshot)
        snapshot.peers.require_active(identity.origin, epoch=identity.epoch)
    except SyncWorkspaceError:
        metadata['error'] = 'invalid_snapshot'
    except FullResyncRequired:
        metadata['error'] = 'requires_full_resync'


def _workspace_state(outbox: dict[str, object], control: dict[str, object], coordination: dict[str, object],
                     conflicts: list[tuple[str, str]], unresolved: list[tuple[str, str]],
                     pending: int) -> WorkspaceState:
    protocol = _protocol_state(outbox, control, cast(str, coordination['error']))
    if protocol is not None:
        return protocol
    if conflicts:
        return 'conflict'
    if unresolved:
        return 'unresolved'
    return 'pending' if pending else 'ready'


def _protocol_state(outbox: dict[str, object], control: dict[str, object], error: str) -> WorkspaceState | None:
    known: dict[str, WorkspaceState] = {'invalid_snapshot': 'invalid', 'invalid_pending': 'invalid',
        'configuration_changed': 'invalid', 'requires_full_resync': 'requires_full_resync',
        'missing_baseline': 'requires_full_resync', 'network_error': 'offline'}
    if error in known:
        return known[error]
    for label, state in (('blocked', 'requires_full_resync'), ('offline', 'offline'), ('conflict', 'conflict')):
        if outbox[label] or control['state'] == label:
            return cast(WorkspaceState, state)
    return None
