"""Strict workspace HTTP requests refresh live credentials, authority and lease checkpoints before every RPC."""
from __future__ import annotations

import math
import os
import re
from typing import Callable, Optional

from je_auto_control.utils.config_sync.causal_client import CausalSyncClient
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.config_sync.http_commands import _client, _options, _retry_policy
from je_auto_control.utils.config_sync.workspace_config import WorkspaceSpec
from je_auto_control.utils.config_sync.workspace_models import SyncWorkspaceError, validate_workspace_snapshot
from je_auto_control.utils.logging.secret_scope import remember_secret


def network_options(value: Optional[dict[str, object]]) -> dict[str, object]:
    """Validate cheap option grammar without resolving a credential or opening a connection."""
    result = _options(value, ('policy', 'max_rebases'))
    _timeout(result.get('timeout_s', 5.0))
    _credential(result.get('secret_env'))
    _rebases(result.get('max_rebases', 3))
    _retry_policy(result.get('policy'))
    return result


def _timeout(timeout: object) -> None:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 300:
        raise ConfigSyncError('workspace timeout must be a finite positive number up to 300 seconds')
    if not math.isfinite(timeout):
        raise ConfigSyncError('workspace timeout must be finite')

def _credential(environment: object) -> None:
    if environment is not None and (not isinstance(environment, str)
                                   or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', environment) is None):
        raise ConfigSyncError('secret_env must name one environment variable')

def _rebases(rebases: object) -> None:
    if isinstance(rebases, bool) or not isinstance(rebases, int) or not 0 <= rebases <= 10:
        raise ConfigSyncError('workspace rebasing allows 0–10 definite stale-base retries')


class WorkspaceClient(CausalSyncClient):
    """Keep credentials out of workspace state while refusing invalid snapshots before prepare/confirmation."""

    def __init__(self, spec: WorkspaceSpec, options: dict[str, object], checkpoint: Callable[[], None]) -> None:
        super().__init__(spec.endpoint, user_id=spec.user_id, snapshot_validator=validate_workspace_snapshot)
        self._options = options
        self._checkpoint = checkpoint

    def _request(self, method: str, body: Optional[dict[str, object]] = None) -> dict[str, object]:
        self._checkpoint()
        delegate = _client(self._endpoint, self._user_id, self._options)
        # pylint: disable-next=protected-access  # reason: this package keeps each live transport credential in its caller's secret scope
        remember_secret(delegate._secret or '')
        if body is not None:
            _validate_envelope(body)
        try:
            # pylint: disable-next=protected-access  # reason: reuse the shared bounded causal wire without recursive workspace callbacks
            return delegate._request(method, body)
        finally:
            environment = self._options.get('secret_env')
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
