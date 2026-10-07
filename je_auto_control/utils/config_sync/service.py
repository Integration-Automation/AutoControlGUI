"""Shared explicit preview, protected exchange, apply, retry and status services."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Event
from typing import Any, Dict, Optional, Tuple

from je_auto_control.utils.path_guard.policy import scoped_path
from je_auto_control.utils.rbac.authorization import require_command

from .causal_bucket import bucket_peer_states, merge_causal_buckets
from .apply_service import config_sync_apply
from .client import ConfigSyncClient, SyncClientOptions, SyncRecoveryRequired, SyncValidationError
from .definition_files import (
    SECTIONS, ensure_portable_bucket, read_object, snapshot_definitions, write_object,
)
from .models import ConfigBucket, ConfigSyncError
from .outbox import normalize_endpoint


def _paths(workspace_path: str, server_url: str, user_id: str) -> Tuple[Path, Path, Path]:
    identity = hashlib.sha256(json.dumps([normalize_endpoint(server_url), user_id]).encode('utf-8')).hexdigest()
    root = scoped_path(workspace_path, operation='write') / identity
    return (scoped_path(root / 'state.json', operation='write'),
            scoped_path(root / 'preview.json', operation='write'),
            scoped_path(root / 'outbox.sqlite', operation='write'))


def _client(server_url: str, user_id: str, outbox: Path, secret: str) -> ConfigSyncClient:
    outbox.parent.mkdir(parents=True, exist_ok=True)
    return ConfigSyncClient(server_url, user_id=user_id, secret=secret,
                            options=SyncClientOptions(outbox_path=outbox, acknowledge_on_sync=False,
                                                       bucket_validator=ensure_portable_bucket))


def _conflicts(bucket: ConfigBucket) -> int:
    return sum('sync_conflict' in value for section in SECTIONS for value in bucket.sections.get(section, {}).values())


def _status(client: ConfigSyncClient, bucket: ConfigBucket, *, offline: bool = False) -> Dict[str, Any]:
    known = next((peer.acknowledged_revision for peer in bucket_peer_states(bucket)
                  if peer.peer_id == client.device_id), 0)
    return {'revision': bucket.revision, 'pending': len(client.pending_operations()), 'conflicts': _conflicts(bucket),
            'offline': offline, 'cas_supported': client.cas_supported,
            'last_successful_revision': max(known, client.last_successful_revision), 'device_id': client.device_id,
            'applied_revision': known, 'recovery': client.recovery_status()}


def _exchange(definitions_path: str, workspace_path: str, server_url: str, user_id: str, secret: str, *,
              publish: bool, cancel: Optional[Event]) -> Dict[str, Any]:
    state_path, preview_path, outbox = _paths(workspace_path, server_url, user_id)
    client = _client(server_url, user_id, outbox, secret)
    try:
        local, digest = snapshot_definitions(Path(definitions_path), state_path, user_id, client.device_id)
        if cancel is not None and cancel.is_set():
            return {**_status(client, local, offline=True), 'cancelled': True}
        if publish:
            client.queue(local)
        try:
            merged = _exchange_bucket(client, local, publish=publish, cancel=cancel)
        except SyncValidationError:
            raise
        except SyncRecoveryRequired as error:
            return {**_status(client, local), 'recovery_required': str(error), 'cancelled': False}
        except ConfigSyncError:
            return {**_status(client, local, offline=True), 'cancelled': cancel is not None and cancel.is_set()}
        if publish:
            # Receipt advances preview/registry state; applied entry heads and acknowledgement stay local.
            local.revision = merged.revision
            local.sections['__sync_devices__'] = merged.sections.get('__sync_devices__', {})
            write_object(state_path, local.to_dict())
        write_object(preview_path, {'definitions_sha256': digest, 'bucket': merged.to_dict(),
                                    'device_id': client.device_id})
        return {**_status(client, merged), 'preview_path': str(preview_path), 'state_path': str(state_path),
                'definitions_sha256': digest, 'bucket': merged.to_dict(), 'cancelled': False}
    finally:
        client.close()


def _exchange_bucket(client: ConfigSyncClient, local: ConfigBucket, *, publish: bool,
    cancel: Optional[Event]) -> ConfigBucket:
    remote = client.fetch() or ConfigBucket(local.user_id)
    try:
        ensure_portable_bucket(remote)
    except ConfigSyncError as error:
        raise SyncValidationError(str(error)) from error
    if publish:
        merged, _ = client.sync(local, cancel=cancel)
    else:
        merged, _ = merge_causal_buckets(local, remote)
    ensure_portable_bucket(merged)
    return merged


# Empty means no configured credential; it is not a built-in password.
def config_sync_preview(  # nosec B107
    definitions_path: str, workspace_path: str, server_url: str, user_id: str,
    shared_secret: str = '', *, cancel: Optional[Event] = None) -> Dict[str, Any]:
    """Snapshot local definitions and preview causal alternatives without publishing or applying."""
    require_command('AC_config_sync_preview')
    return _exchange(definitions_path, workspace_path, server_url, user_id, shared_secret,
                     publish=False, cancel=cancel)


# Empty means no configured credential; it is not a built-in password.
def config_sync_exchange(  # nosec B107
    definitions_path: str, workspace_path: str, server_url: str, user_id: str,
    shared_secret: str = '', *, cancel: Optional[Event] = None) -> Dict[str, Any]:
    """Publish protected portable definitions; local application remains a separate explicit action."""
    require_command('AC_config_sync_exchange')
    return _exchange(definitions_path, workspace_path, server_url, user_id, shared_secret,
                     publish=True, cancel=cancel)


# Empty means no configured credential; it is not a built-in password.
def config_sync_retry(  # nosec B107
    workspace_path: str, server_url: str, user_id: str, shared_secret: str = '', *,
    cancel: Optional[Event] = None) -> Dict[str, Any]:
    """Retry durable envelopes with bounded attempts; keep failed or uncertain operations intact."""
    require_command('AC_config_sync_retry')
    _, _, outbox = _paths(workspace_path, server_url, user_id)
    client = _client(server_url, user_id, outbox, shared_secret)
    try:
        report = client.retry_pending(cancel=cancel)
        return {'sent': report.sent, 'pending': report.pending, 'conflicts': report.conflicts,
                'failed': report.failed, 'cancelled': report.cancelled,
                'last_successful_revision': client.last_successful_revision}
    finally:
        client.close()


def config_sync_status(workspace_path: str, server_url: str, user_id: str) -> Dict[str, Any]:
    """Read local revision and pending counts without network access or secret disclosure."""
    require_command('AC_config_sync_status')
    state_path, _, outbox = _paths(workspace_path, server_url, user_id)
    client = _client(server_url, user_id, outbox, '')
    try:
        state = read_object(state_path, missing=True)
        bucket = ConfigBucket.from_dict(state) if state else ConfigBucket(user_id)
        return _status(client, bucket, offline=True)
    finally:
        client.close()

__all__ = ['config_sync_preview', 'config_sync_exchange', 'config_sync_apply',
           'config_sync_retry', 'config_sync_status']
