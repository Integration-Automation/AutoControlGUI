"""Config HTTP client and compatible legacy timestamp merge."""
from __future__ import annotations
import json
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Dict, List, Mapping, Optional, Tuple
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.http_client import http_client
from .models import TOMBSTONE_RETENTION_S, ConfigBucket, ConfigSyncError, ConflictRecord, is_tombstone
from .database import StorePath
from .store import ConfigRevisionConflict, validate_revision
from .outbox import OutboxReport, SyncOperation, SyncOutbox
from .causal_bucket import (
    BucketConflict, bucket_peer_states, collect_acknowledged_tombstones, merge_causal_buckets,
    device_requires_full_sync, prepare_tombstone_revisions, update_peer_state,
)
from .versions import PeerState

_DEFAULT_TIMEOUT_S = 5.0


def _default_outbox_path() -> Path:
    return Path.home() / '.je_auto_control' / 'config_outbox.sqlite'


@dataclass(frozen=True)
class SyncClientOptions:
    """Client migration, persistent retry path and optional explicit device identity."""
    outbox_path: StorePath = _default_outbox_path
    device_id: Optional[str] = None
    legacy_writes: bool = False
    max_cas_retries: int = 3


@dataclass
class _ClientSyncState:
    cas_supported: bool = False
    last_successful_revision: int = 0

def merge_buckets(local: ConfigBucket,
                  remote: ConfigBucket,
                  *, now: Optional[float] = None,
                  tombstone_retention_s: float = TOMBSTONE_RETENTION_S,
                  ) -> Tuple[ConfigBucket, List[ConflictRecord]]:
    """Last-write-wins merge across every section. Returns merged + conflicts.

    Tombstones take part like any other entry, so a deletion newer than a
    remote copy removes it and an edit newer than a deletion restores it.
    Tombstones older than ``tombstone_retention_s`` (measured from ``now``,
    default the current time) are left out of the result.
    """
    if local.user_id != remote.user_id:
        raise ConfigSyncError(
            f"user_id mismatch: local={local.user_id!r} remote={remote.user_id!r}",
        )
    merged = ConfigBucket(user_id=local.user_id)
    conflicts: List[ConflictRecord] = []
    sections = set(local.sections) | set(remote.sections)
    for name in sections:
        local_sec = local.sections.get(name, {})
        remote_sec = remote.sections.get(name, {})
        merged_section, section_conflicts = _merge_legacy_section(name, local_sec, remote_sec)
        conflicts.extend(section_conflicts)
        merged.sections[name] = _without_expired(
            merged_section, (time.time() if now is None else now) - tombstone_retention_s)
    merged.revision = max(local.revision, remote.revision) + 1
    return merged, conflicts


def _merge_legacy_section(name: str, local: Mapping[str, Dict[str, Any]], remote: Mapping[str, Dict[str, Any]]
                          ) -> Tuple[Dict[str, Dict[str, Any]], List[ConflictRecord]]:
    merged: Dict[str, Dict[str, Any]] = {}
    conflicts = []
    for entry_id in local.keys() | remote.keys():
        left, right = local.get(entry_id), remote.get(entry_id)
        if left is None:
            if right is not None:
                merged[entry_id] = right
            continue
        if right is None:
            merged[entry_id] = left
            continue
        kept, dropped = _winner(left, right)
        merged[entry_id] = kept
        if dropped is not None:
            conflicts.append(ConflictRecord(name, entry_id, dropped, kept))
    return merged, conflicts


def _winner(local_entry: Dict[str, Any], remote_entry: Dict[str, Any],
            ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """The entry that wins and the one it beat (``None`` when they are equal).

    The later ``last_modified`` wins. At a tie a deletion wins -- ``delete``
    stamps its tombstone no earlier than the entry it removes -- and then the
    larger canonical JSON, so both sides pick the same entry: "local wins"
    had two clients each push their own copy on every sync, never agreeing
    and never reporting the conflict.
    """
    local_ts = float(local_entry.get("last_modified", 0))
    remote_ts = float(remote_entry.get("last_modified", 0))
    if local_ts != remote_ts:
        if remote_ts > local_ts:
            return remote_entry, local_entry
        return local_entry, remote_entry
    if local_entry == remote_entry:
        return local_entry, None
    loser, winner = sorted((local_entry, remote_entry), key=_tie_rank)
    return winner, loser


def _tie_rank(entry: Dict[str, Any]) -> Tuple[bool, str]:
    return is_tombstone(entry), json.dumps(entry, sort_keys=True, default=str)


def _without_expired(section: Dict[str, Dict[str, Any]],
                     cutoff: float) -> Dict[str, Dict[str, Any]]:
    return {entry_id: entry for entry_id, entry in section.items()
            if not (is_tombstone(entry) and float(entry.get("last_modified", 0)) < cutoff)}


class ConfigSyncClient:
    """Stdlib HTTP client for the signaling server's ``/config`` endpoints.

    Methods are intentionally small and synchronous — the GUI wraps
    them in QThread workers when wiring up periodic sync.
    """

    def __init__(self, server_url: str, *,
                 user_id: str, secret: Optional[str] = None,
                 timeout_s: float = _DEFAULT_TIMEOUT_S,
                 options: Optional[SyncClientOptions] = None) -> None:
        if not server_url:
            raise ConfigSyncError("server_url is required")
        if not user_id:
            raise ConfigSyncError("user_id is required")
        self._server_url = server_url.rstrip("/")
        self._user_id = user_id
        self._secret = secret
        self._timeout = float(timeout_s)
        self._options = options or SyncClientOptions()
        self._outbox = SyncOutbox(self._options.outbox_path, endpoint=self._server_url, user_id=user_id)
        self._state = _ClientSyncState()
        if not isinstance(self._options.max_cas_retries, int) or self._options.max_cas_retries < 1:
            raise ConfigSyncError('max_cas_retries must be positive')

    def _endpoint(self, suffix: str = "") -> str:
        encoded = urllib.parse.quote(self._user_id, safe="")
        path = f"/config/{encoded}{suffix}"
        return f"{self._server_url}{path}"

    def _request(self, method: str, *,
                 body: Optional[Mapping[str, Any]] = None,
                 ) -> Optional[Dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if self._secret:
            headers["X-Signaling-Secret"] = self._secret
        data = json.dumps(body).encode("utf-8") if body is not None else None
        try:
            call = http_client.build_call(self._endpoint(), method=method, headers=headers,
                              data=data, timeout=self._timeout)
            # Through http_client for the egress policy and the body cap, and
            # without following redirects: urlopen carried X-Signaling-Secret
            # to whatever host a redirect named.
            call["follow_redirects"] = False
            response = http_client.perform_call(call)
        except (OSError, ValueError, AutoControlException) as error:
            raise ConfigSyncError(f"config sync {method} failed: {error}") from error
        status = int(response["status"])
        if status == 404:
            return None
        if status == 409:
            raise ConfigRevisionConflict('config sync PUT used a stale revision')
        if not 200 <= status < 300:
            raise ConfigSyncError(f"config sync {method} returned HTTP {status}")
        if not response.get("text"):
            return {}
        try:
            reply = json.loads(response["text"])
            if not isinstance(reply, dict):
                raise ConfigSyncError('config sync reply must be an object')
            return reply
        except (json.JSONDecodeError, RecursionError) as error:
            raise ConfigSyncError("config sync: invalid JSON reply") from error

    def fetch(self) -> Optional[ConfigBucket]:
        """GET the bucket from the server, or ``None`` when none exists."""
        body = self._request("GET")
        if body is None:
            return None
        bucket = ConfigBucket.from_dict(body)
        if bucket.user_id != self._user_id:
            raise ConfigSyncError('server bucket user_id mismatch')
        self._state.cas_supported = body.get('cas_supported') is True and body.get('schema_version') == 2
        return bucket

    def push(self, bucket: ConfigBucket, *, base_revision: Optional[int] = None,
             operation_id: Optional[str] = None) -> int:
        """Persist a protected write before dispatch; uncertain replies retain the exact envelope."""
        if bucket.user_id != self._user_id:
            raise ConfigSyncError(
                f"bucket user_id={bucket.user_id!r} mismatches client user_id"
                f"={self._user_id!r}",
            )
        if self._options.legacy_writes:
            self._request('PUT', body=bucket.to_dict())
            return bucket.revision
        self._check_retirement(self.fetch())
        return self._push_protected(bucket, base_revision=base_revision, operation_id=operation_id)

    def _push_protected(self, bucket: ConfigBucket, *, base_revision: Optional[int] = None,
                        operation_id: Optional[str] = None) -> int:
        base = bucket.revision if base_revision is None else base_revision
        prepared = prepare_tombstone_revisions(bucket, base)
        operation = SyncOperation(self._server_url, self._user_id, operation_id or uuid.uuid4().hex,
                                  base, prepared.to_dict())
        self._outbox.enqueue(operation)
        try:
            revision = self._dispatch_operation(operation)
        except ConfigRevisionConflict:
            self._outbox.mark_conflict(operation.operation_id)
            raise
        self._outbox.confirm(operation.operation_id, revision=revision)
        self._state.last_successful_revision = revision
        return revision

    def _dispatch_operation(self, operation: SyncOperation) -> int:
        reply = self._request('PUT', body=operation.envelope())
        if reply is None or reply.get('cas_supported') is not True or reply.get('schema_version') != 2:
            raise ConfigSyncError('server did not confirm version-2 competition protection')
        revision = validate_revision(reply.get('revision'))
        if revision == 0:
            raise ConfigSyncError('server did not confirm a committed revision')
        self._state.cas_supported = True
        self._state.last_successful_revision = revision
        return revision

    def pending_operations(self) -> Tuple[SyncOperation, ...]:
        """Read durable pending, offline and conflict envelopes for this account/endpoint."""
        return self._outbox.pending()

    @property
    def cas_supported(self) -> bool:
        """Whether the last server response confirmed competition protection."""
        return self._state.cas_supported

    @property
    def last_successful_revision(self) -> int:
        """The latest committed revision confirmed during this client lifetime."""
        return self._state.last_successful_revision

    def retry_pending(self, *, cancel: Optional[Event] = None) -> OutboxReport:
        """Retry exact pending envelopes with bounded backoff, preserving unresolved data."""
        self._check_retirement(self.fetch())
        return self._outbox.drain(self._dispatch_operation, cancel=cancel)

    @property
    def device_id(self) -> str:
        """Return the explicit or durable local origin without relying on a machine clock."""
        return self._options.device_id or self._outbox.device_id()

    def close(self) -> None:
        """Release local retry storage without deleting undelivered data."""
        self._outbox.close()

    def sync(self, local: ConfigBucket
             ) -> Tuple[ConfigBucket, List[ConflictRecord]] | Tuple[ConfigBucket, List[BucketConflict]]:
        """Fetch and merge causally, then commit with finite CAS retries; legacy mode is explicit."""
        if not self._options.legacy_writes:
            return self._sync_causal(local)
        remote = self.fetch() or ConfigBucket(user_id=self._user_id)
        merged, conflicts = merge_buckets(local, remote)
        self.push(merged)
        return merged, conflicts

    def _sync_causal(self, local: ConfigBucket) -> Tuple[ConfigBucket, List[BucketConflict]]:
        self._check_retirement(self.fetch())
        if self.pending_operations():
            self.retry_pending()
            if self.pending_operations():
                raise ConfigSyncError('pending operations require delivery or conflict resolution first')
        old_operation: Optional[str] = None
        for _attempt in range(self._options.max_cas_retries):
            remote = self.fetch() or ConfigBucket(self._user_id)
            self._check_retirement(remote)
            merged, conflicts = merge_causal_buckets(local, remote)
            merged = collect_acknowledged_tombstones(merged, bucket_peer_states(remote))
            merged = prepare_tombstone_revisions(merged, remote.revision)
            update_peer_state(merged, PeerState(self.device_id, remote.revision + 1), device_id=self.device_id)
            operation_id = uuid.uuid4().hex
            operation = SyncOperation(self._server_url, self._user_id, operation_id, remote.revision, merged.to_dict())
            self._outbox.enqueue(operation)
            if old_operation is not None:
                self._outbox.drop_conflict(old_operation)
            try:
                merged.revision = self.push(merged, base_revision=remote.revision, operation_id=operation_id)
            except ConfigRevisionConflict:
                old_operation = operation_id
                continue
            self._outbox.acknowledge_peer(self.device_id, revision=merged.revision)
            return merged, conflicts
        raise ConfigRevisionConflict('config sync exhausted bounded CAS retries')

    def _check_retirement(self, remote: Optional[ConfigBucket]) -> None:
        if (self._outbox.requires_full_sync(self.device_id)
                or device_requires_full_sync(remote, self.device_id)):
            raise ConfigSyncError('retired device requires a full sync before incremental edits')

    def retire_device(self, device_id: str) -> int:
        """Explicitly retire a known device in the shared registry before deleting its tombstone obligations."""
        remote = self.fetch()
        if remote is None:
            raise ConfigSyncError('no shared device registry')
        peers = {peer.peer_id: peer for peer in bucket_peer_states(remote)}
        if device_id not in peers:
            raise ConfigSyncError('unknown device')
        update_peer_state(remote, PeerState(device_id, peers[device_id].acknowledged_revision, True),
                          device_id=self.device_id)
        revision = self.push(remote, base_revision=remote.revision)
        self._outbox.retire_peer(device_id)
        return revision

    def full_resync(self) -> ConfigBucket:
        """Explicitly obtain the full server snapshot and reactivate this device without old incremental edits."""
        if self.pending_operations():
            raise ConfigSyncError('review pending operations before a full sync')
        for _attempt in range(self._options.max_cas_retries):
            remote = self.fetch()
            if remote is None or not self.cas_supported:
                raise ConfigSyncError('full sync requires a protected server snapshot')
            base = remote.revision
            update_peer_state(remote, PeerState(self.device_id, base + 1), device_id=self.device_id)
            try:
                remote.revision = self._push_protected(remote, base_revision=base)
            except ConfigRevisionConflict:
                # A confirmed stale full snapshot must never be applied or revived.
                for operation in self.pending_operations():
                    self._outbox.drop_conflict(operation.operation_id)
                continue
            self._outbox.complete_full_sync(self.device_id, revision=remote.revision)
            return remote
        raise ConfigRevisionConflict('full sync exhausted bounded CAS retries')


__all__ = [
    "ConfigBucket", "ConflictRecord", "ConfigSyncClient",
    "ConfigSyncError", "TOMBSTONE_RETENTION_S", "is_tombstone", "merge_buckets",
]
