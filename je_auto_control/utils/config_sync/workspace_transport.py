"""Strict workspace HTTP requests refresh live credentials, authority and lease checkpoints before every RPC."""
from __future__ import annotations

import os
from typing import Callable, Iterable, Optional

from je_auto_control.utils.config_sync.causal_client import CausalSyncClient
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.causal_receipt import CausalReceipt
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.config_sync.http_commands import _client
from je_auto_control.utils.config_sync.workspace_config import WorkspaceSpec
from je_auto_control.utils.config_sync.workspace_assets import WorkspaceHTTPContext
from je_auto_control.utils.config_sync.outbox import SyncOutbox
from je_auto_control.utils.config_sync.outbox_models import SyncOperation
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.config_sync.workspace_options import network_options as _network_options
from je_auto_control.utils.config_sync.workspace_models import SyncWorkspaceError, validate_workspace_snapshot
from je_auto_control.utils.logging.secret_scope import remember_secret


def network_options(value: Optional[dict[str, object]]) -> dict[str, object]:
    """Preserve the original option-validation import path while sharing cheap validation with asset HTTP."""
    return _network_options(value)


class WorkspaceClient(CausalSyncClient):
    """Keep credentials out of workspace state while refusing invalid snapshots before prepare/confirmation."""

    def __init__(self, spec: WorkspaceSpec, options: dict[str, object], checkpoint: Callable[[], None]) -> None:
        super().__init__(spec.endpoint, user_id=spec.user_id, snapshot_validator=validate_workspace_snapshot)
        self._runtime = WorkspaceHTTPContext(spec, options, checkpoint)

    def _deliver(self, outbox: SyncOutbox, operation: SyncOperation, max_rebases: int,
                   cancelled: Optional[Callable[[], bool]]) -> CausalReceipt:
        if operation.prepared is None:
            self._runtime.upload(operation)
        return super()._deliver(outbox, operation, max_rebases, cancelled)

    def download_assets(self, entries: Iterable[SyncEntry]) -> None:
        """Fill only missing immutable bytes for selected cached heads without activating any definition."""
        self._runtime.download(entries)

    def _request(self, method: str, body: Optional[dict[str, object]] = None) -> dict[str, object]:
        self._runtime.checkpoint()
        delegate = _client(self._endpoint, self._user_id, self._runtime.options)
        # pylint: disable-next=protected-access  # reason: this package keeps each live transport credential in its caller's secret scope
        remember_secret(delegate._secret or '')
        if body is not None:
            _validate_envelope(body)
        try:
            # pylint: disable-next=protected-access  # reason: reuse the shared bounded causal wire without recursive workspace callbacks
            return delegate._request(method, body)
        finally:
            environment = self._runtime.options.get('secret_env')
            if isinstance(environment, str):
                remember_secret(os.environ.get(environment, ''))


def _validate_envelope(body: dict[str, object]) -> None:
    try:
        raw = body.get('bucket')
        if not isinstance(raw, dict):
            raise ConfigSyncError('invalid workspace request bucket')
        bucket = dict(raw)
        bucket.pop('_actor', None)
        snapshot = CausalBucket.from_dict(bucket)
    except ConfigSyncError as error:
        raise SyncWorkspaceError('invalid workspace request snapshot', code='invalid_snapshot') from error
    validate_workspace_snapshot(snapshot)
