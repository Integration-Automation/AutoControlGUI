"""HTTP client for the config-sync bucket.

The bucket model and the error types live in :mod:`.bucket` and the merges in
:mod:`.merge`; every name that used to be defined here is still importable
from here.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, Tuple

from je_auto_control.utils.config_sync.bucket import (
    TOMBSTONE_RETENTION_S, WIRE_VERSION, ConfigBucket, ConfigSyncConflict, ConfigSyncError,
    FullResyncRequired, OperationMismatchError, is_tombstone, new_operation_id,
)
from je_auto_control.utils.config_sync.merge import (
    ConflictRecord, apply_operation, awaits_ack, batch_operation_id, merge_buckets, settle,
)
from je_auto_control.utils.exception.exceptions import AutoControlException

if TYPE_CHECKING:
    from je_auto_control.utils.config_sync.versions import SyncConflict, SyncOperation

_DEFAULT_TIMEOUT_S = 5.0
#: How often :meth:`ConfigSyncClient.sync` fetches, merges and pushes again
#: after losing a race to another machine before it gives up.
DEFAULT_SYNC_ATTEMPTS = 4


@dataclass
class SyncResult:
    """What :meth:`ConfigSyncClient.push_operations` left on the server.

    ``bucket`` is the server's state including this device's operations,
    ``revision`` its committed revision, ``conflicts`` the keys where an
    operation met a concurrent change (both kept), and ``pushed`` whether a
    write was needed at all.
    """
    bucket: ConfigBucket
    revision: int
    conflicts: List["SyncConflict"] = field(default_factory=list)
    pushed: bool = False


class ConfigSyncClient:
    """Stdlib HTTP client for the signaling server's ``/config`` endpoints.

    Methods are intentionally small and synchronous — the GUI wraps
    them in QThread workers when wiring up periodic sync.
    """

    def __init__(self, server_url: str, *,
                 user_id: str, secret: Optional[str] = None,
                 timeout_s: float = _DEFAULT_TIMEOUT_S,
                 device_id: Optional[str] = None) -> None:
        if not server_url:
            raise ConfigSyncError("server_url is required")
        if not user_id:
            raise ConfigSyncError("user_id is required")
        self._server_url = server_url.rstrip("/")
        self._user_id = user_id
        self._secret = secret
        self._timeout = float(timeout_s)
        self._device_id = device_id or None

    @property
    def device_id(self) -> str:
        """The device :meth:`sync` announces: the one given, else this machine's.

        The default is read (and on a machine's very first use created) when
        it is first needed, not when the client is built.
        """
        if self._device_id is None:
            from je_auto_control.utils.config_sync import device
            self._device_id = device.default_device_id()
        return self._device_id

    @property
    def user_id(self) -> str:
        """The account this client syncs."""
        return self._user_id

    @property
    def server_url(self) -> str:
        """The server this client talks to, without a trailing slash."""
        return self._server_url

    @property
    def timeout_s(self) -> float:
        """Seconds this client waits for one request."""
        return self._timeout

    def _endpoint(self, suffix: str = "") -> str:
        encoded = urllib.parse.quote(self._user_id, safe="")
        path = f"/config/{encoded}{suffix}"
        return f"{self._server_url}{path}"

    def _request(self, method: str, *,
                 body: Optional[Mapping[str, Any]] = None,
                 ) -> Optional[Dict[str, Any]]:
        from je_auto_control.utils.http_client.http_client import build_call, perform_call
        headers = {"Content-Type": "application/json"}
        if self._secret:
            headers["X-Signaling-Secret"] = self._secret
        data = json.dumps(body).encode("utf-8") if body is not None else None
        try:
            call = build_call(self._endpoint(), method=method, headers=headers,
                              data=data, timeout=self._timeout)
            # Through http_client for the egress policy and the body cap, and
            # without following redirects: urlopen carried X-Signaling-Secret
            # to whatever host a redirect named.
            call["follow_redirects"] = False
            response = perform_call(call)
        except (OSError, ValueError, AutoControlException) as error:
            raise ConfigSyncError(f"config sync {method} failed: {error}") from error
        status = int(response["status"])
        if status == 404:
            return None
        if status == 409:
            raise _refusal(method, response.get("text"), body)
        if status == 428:
            raise ConfigSyncError(
                f"config sync {method} returned HTTP 428: the server only accepts "
                "revision-checked (version 2) writes")
        if not 200 <= status < 300:
            raise ConfigSyncError(f"config sync {method} returned HTTP {status}")
        if not response.get("text"):
            return {}
        try:
            return json.loads(response["text"])
        except (json.JSONDecodeError, RecursionError) as error:
            raise ConfigSyncError("config sync: invalid JSON reply") from error

    def fetch(self) -> Optional[ConfigBucket]:
        """GET the bucket from the server, or ``None`` when none exists."""
        body = self._request("GET")
        if body is None:
            return None
        return ConfigBucket.from_dict(body)

    def push(self, bucket: ConfigBucket, *, base_revision: Optional[int] = None,
             operation_id: Optional[str] = None) -> int:
        """PUT the bucket if the server is still at ``base_revision``.

        ``base_revision`` defaults to ``bucket.revision`` -- for a bucket
        that came from :meth:`fetch` that is the revision it was read at;
        ``0`` means "there is no bucket yet". Returns the committed revision
        and stores it in ``bucket.revision``. Raises
        :class:`ConfigSyncConflict` when another machine pushed in between;
        nothing is overwritten. Pass the same ``operation_id`` when repeating
        a push whose reply never arrived: the server answers with the
        revision the first attempt produced instead of a conflict. Reusing
        an id for a different bucket or base revision raises
        :class:`OperationMismatchError`.
        """
        if bucket.user_id != self._user_id:
            raise ConfigSyncError(
                f"bucket user_id={bucket.user_id!r} mismatches client user_id"
                f"={self._user_id!r}",
            )
        base = bucket.revision if base_revision is None else int(base_revision)
        reply = self._request("PUT", body={
            "version": WIRE_VERSION, "base_revision": base,
            "operation_id": operation_id or new_operation_id(),
            "bucket": bucket.to_dict(),
        })
        revision = (reply or {}).get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int):
            # A server from before the version-2 format stores any JSON
            # object and answers {"ok": true}: it did not check anything.
            raise ConfigSyncError(
                "config sync PUT: the server did not report a committed revision; "
                "it predates revision-checked writes and must be upgraded")
        bucket.revision = revision
        return revision

    def sync(self, local: ConfigBucket, *, max_attempts: int = DEFAULT_SYNC_ATTEMPTS,
             now: Optional[float] = None) -> Tuple[ConfigBucket, List[ConflictRecord]]:
        """Bidirectional sync: fetch, merge, push on top of what was fetched.

        When another machine pushes between the fetch and the push the
        server refuses the write, and this fetches and merges again -- up to
        ``max_attempts`` times, then :class:`ConfigSyncConflict`. The
        returned bucket's ``revision`` is the one the server committed.

        The push records :attr:`device_id` under the bucket's ``peers`` as
        having merged that revision, exactly as :meth:`push_operations`
        does: deletions wait for this device before they are forgotten, and
        the ones every device has seen are dropped. Raises
        :class:`FullResyncRequired` when the group has retired this device.
        """
        device = self.device_id
        stamp = time.time() if now is None else float(now)
        for _attempt in range(max(1, int(max_attempts))):
            remote = self.fetch() or ConfigBucket(user_id=self._user_id)
            self._require_active(remote, device)
            merged, conflicts = merge_buckets(local, remote)
            settle(merged, device, remote.revision + 1, stamp, None)
            try:
                self.push(merged, base_revision=remote.revision)
            except ConfigSyncConflict:
                continue
            return merged, conflicts
        raise ConfigSyncConflict(
            f"config sync: still behind the server after {max_attempts} attempts")

    def push_operations(self, operations: Sequence["SyncOperation"], *, device_id: str,
                        max_attempts: int = DEFAULT_SYNC_ATTEMPTS, now: Optional[float] = None,
                        max_offline_s: Optional[float] = None) -> SyncResult:
        """Apply this device's pending changes on top of the server's state.

        Fetches the bucket, merges each operation into it by causality
        (a concurrent change to the same key is kept beside it as a
        conflict), records that ``device_id`` has merged the result, and
        commits against the fetched revision -- fetching again when another
        device got there first, up to ``max_attempts`` times. Applying the
        same operations twice changes nothing, so a batch can be resent
        after an uncertain failure. With no operations this still pushes
        when the bucket holds a deletion this device has not acknowledged,
        or to list a device the bucket does not know yet -- unless the
        bucket holds no entries, when there is nothing to commit and
        ``pushed`` is false.

        Raises :class:`FullResyncRequired` when the group has retired this
        device. ``max_offline_s`` retires peers not seen for that long.
        """
        if not device_id:
            raise ConfigSyncError("device_id is required")
        stamp = time.time() if now is None else float(now)
        for _attempt in range(max(1, int(max_attempts))):
            remote = self.fetch() or ConfigBucket(user_id=self._user_id)
            self._require_active(remote, device_id)
            merged = ConfigBucket.from_dict(remote.to_dict())
            conflicts: List["SyncConflict"] = []
            changed = [apply_operation(merged, operation, conflicts) for operation in operations]
            if not any(changed) and not awaits_ack(remote, device_id):
                return SyncResult(bucket=remote, revision=remote.revision, conflicts=conflicts)
            settle(merged, device_id, remote.revision + 1, stamp, max_offline_s)
            try:
                revision = self.push(merged, base_revision=remote.revision,
                                     operation_id=batch_operation_id(remote.revision, operations))
            except ConfigSyncConflict:
                continue
            return SyncResult(bucket=merged, revision=revision, conflicts=conflicts, pushed=True)
        raise ConfigSyncConflict(
            f"config sync: still behind the server after {max_attempts} attempts")

    def _require_active(self, remote: ConfigBucket, device_id: str) -> None:
        peer = remote.peer_states().get(device_id)
        if peer is not None and peer.retired:
            raise FullResyncRequired(
                f"device {device_id!r} was retired from the bucket of {self._user_id!r}; "
                "call full_resync() and replace the local state")

    def retire_peer(self, device_id: str, *, max_attempts: int = DEFAULT_SYNC_ATTEMPTS) -> int:
        """Stop waiting for ``device_id``; returns the committed revision.

        Tombstones no longer wait for a retired device, and it is refused
        with :class:`FullResyncRequired` until it does a full resync.
        """
        from je_auto_control.utils.config_sync.versions import PeerState
        for _attempt in range(max(1, int(max_attempts))):
            remote = self.fetch() or ConfigBucket(user_id=self._user_id)
            known = remote.peer_states().get(device_id) or PeerState(device_id)
            remote.peers[device_id] = PeerState(
                device_id, known.acked_revision, known.last_seen, retired=True).to_dict()
            try:
                return self.push(remote)
            except ConfigSyncConflict:
                continue
        raise ConfigSyncConflict(
            f"config sync: still behind the server after {max_attempts} attempts")

    def full_resync(self, *, device_id: str, max_attempts: int = DEFAULT_SYNC_ATTEMPTS,
                    now: Optional[float] = None) -> ConfigBucket:
        """Re-admit ``device_id`` and return the server's state to adopt.

        The caller must replace its local state with the returned bucket and
        discard its pending operations -- they were made against state the
        group has moved past -- rather than merge the two.
        """
        from je_auto_control.utils.config_sync.versions import PeerState
        stamp = time.time() if now is None else float(now)
        for _attempt in range(max(1, int(max_attempts))):
            remote = self.fetch() or ConfigBucket(user_id=self._user_id)
            remote.peers[device_id] = PeerState(
                device_id, acked_revision=remote.revision + 1, last_seen=stamp).to_dict()
            try:
                self.push(remote)
            except ConfigSyncConflict:
                continue
            return remote
        raise ConfigSyncConflict(
            f"config sync: still behind the server after {max_attempts} attempts")


#: ``code`` of the 409 that refuses an operation id reused for other content.
_OPERATION_MISMATCH = "operation_mismatch"


def _refusal(method: str, text: Any, sent: Optional[Mapping[str, Any]]) -> ConfigSyncError:
    """The error a 409 reply stands for: a stale revision, or a reused operation id."""
    try:
        reply = json.loads(text or "")
    except (json.JSONDecodeError, RecursionError, TypeError):
        reply = None
    reply = reply if isinstance(reply, dict) else {}
    found = reply.get("revision")
    revision = found if isinstance(found, int) and not isinstance(found, bool) else None
    if reply.get("code") == _OPERATION_MISMATCH:
        operation_id = str((sent or {}).get("operation_id") or "")
        return OperationMismatchError(
            f"config sync {method}: operation id {operation_id!r} was already used for a "
            "different write; nothing was written", operation_id=operation_id, revision=revision)
    return ConfigSyncConflict(
        f"config sync {method}: the server is at another revision", revision)


__all__ = [
    "ConfigBucket", "ConflictRecord", "ConfigSyncClient", "ConfigSyncConflict",
    "ConfigSyncError", "DEFAULT_SYNC_ATTEMPTS", "FullResyncRequired",
    "OperationMismatchError", "SyncResult",
    "TOMBSTONE_RETENTION_S", "WIRE_VERSION", "batch_operation_id",
    "is_tombstone", "merge_buckets", "new_operation_id",
]
