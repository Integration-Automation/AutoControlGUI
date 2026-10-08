"""HTTP client + deterministic merge for the config-sync bucket."""
from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.parse
import uuid
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

if TYPE_CHECKING:  # reason: versions imports this module for ConfigSyncError
    from je_auto_control.utils.config_sync.versions import (
        PeerState, SyncConflict, SyncEntry, SyncOperation,
    )

_DEFAULT_TIMEOUT_S = 5.0
#: The ``/config`` wire format: a PUT is an envelope naming the revision it
#: was built on and an operation id, and is refused when that revision is stale.
WIRE_VERSION = 2
#: How often :meth:`ConfigSyncClient.sync` fetches, merges and pushes again
#: after losing a race to another machine before it gives up.
DEFAULT_SYNC_ATTEMPTS = 4

#: How long an *unversioned* deletion is remembered. Entries written with a
#: device id carry a version vector instead, and their tombstones are never
#: dropped by age -- see :func:`~je_auto_control.utils.config_sync.versions.collect_tombstones`.
TOMBSTONE_RETENTION_S = 30 * 24 * 3600.0


def is_tombstone(entry: Mapping[str, Any]) -> bool:
    """Whether ``entry`` records a deletion rather than a value."""
    return entry.get("deleted") is True


class ConfigSyncError(AutoControlException, RuntimeError):
    """Raised on network errors or schema validation failures."""


class ConfigSyncConflict(ConfigSyncError):
    """The server refused a push built on a revision that is no longer current.

    ``revision`` is the server's current revision when it reported one.
    Nothing was written: fetch, merge and push again.
    """

    def __init__(self, message: str, revision: Optional[int] = None) -> None:
        super().__init__(message)
        self.revision = revision


class FullResyncRequired(ConfigSyncError):
    """This device was retired from the group and may not push its old state.

    While it was away the others stopped waiting for it and collected the
    tombstones it never saw, so merging its copy could bring deleted entries
    back. Call :meth:`ConfigSyncClient.full_resync` and replace the local
    state with what it returns.
    """


def new_operation_id() -> str:
    """A fresh id for one push; reuse it when retrying that same push."""
    return uuid.uuid4().hex


@dataclass
class ConflictRecord:
    """One entry on which the two buckets disagreed.

    For unversioned entries ``dropped`` lost a last-modified race to ``kept``.
    With ``unresolved`` true nothing was dropped: the entries were changed
    concurrently on two devices, ``kept`` holds both as ``siblings`` and
    ``dropped`` is the remote side's copy for reference.
    """
    section: str
    entry_id: str
    dropped: Dict[str, Any]
    kept: Dict[str, Any]
    unresolved: bool = False


@dataclass
class ConfigBucket:
    """JSON-shaped bucket persisted on the sync server.

    Each section maps an opaque ``entry_id`` to an entry. An entry written
    with an ``origin`` device id is *versioned*: it has the
    :class:`~je_auto_control.utils.config_sync.versions.SyncEntry` shape
    (``value`` / ``vector`` / ``origin`` / ``operation_id``) and merges by
    causality. An entry written without one is the older flat dict stamped
    with ``last_modified``, which merges by "later wins". Unknown sections
    are passed through untouched.

    A removed entry stays in ``sections`` as a tombstone (``"deleted": true``)
    so the deletion reaches the other machines; read entries through
    :meth:`entries` or :meth:`values`, which leave tombstones out. ``peers``
    records which devices take part and the revision each has merged.
    """
    user_id: str
    sections: Dict[str, Dict[str, Dict[str, Any]]] = field(
        default_factory=dict,
    )
    revision: int = 0
    peers: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, body: Mapping[str, Any]) -> "ConfigBucket":
        if not isinstance(body, Mapping):
            raise ConfigSyncError("bucket body must be a mapping")
        if not isinstance(body.get("user_id"), str):
            raise ConfigSyncError("bucket missing user_id")
        sections = body.get("sections") or {}
        if not isinstance(sections, Mapping):
            raise ConfigSyncError("bucket sections must be a mapping")
        # The server's reply is data, not trusted structure: a list where a
        # section belongs or a non-numeric stamp raised AttributeError or
        # ValueError here or later in merge_buckets.
        return cls(
            user_id=body["user_id"],
            sections={str(name): _section(name, sec) for name, sec in sections.items()},
            revision=int(_finite(body.get("revision", 0), "revision")),
            peers=_peers(body.get("peers") or {}),
        )

    def upsert(self, section: str, entry_id: str,
               entry: Mapping[str, Any], *, origin: Optional[str] = None) -> None:
        """Add or replace an entry.

        With ``origin`` (this device's id) the entry is versioned: the change
        is recorded as made by that device on top of whatever the bucket
        holds for ``entry_id``, and no clock decides later merges.

        Without it the entry is stamped with the current time, and a
        ``last_modified`` already in ``entry`` is kept -- so drop it when
        editing an entry read back from a bucket, otherwise the edit keeps
        its old stamp and loses the merge to any newer remote copy.
        """
        if origin is not None:
            from je_auto_control.utils.config_sync.versions import SyncEntry
            current = self.get_entry(section, entry_id)
            now = time.time()
            self.put_entry(section, (
                SyncEntry.create(entry_id, entry, origin, modified_at=now) if current is None
                else current.edited(entry, origin, modified_at=now)))
            return
        body = dict(entry)
        body["last_modified"] = float(body.get("last_modified", time.time()))
        self.sections.setdefault(section, {})[entry_id] = body

    def remove(self, section: str, entry_id: str, *, origin: Optional[str] = None) -> bool:
        """Replace a live entry with a tombstone; False when there was none.

        Dropping the entry outright let the next sync bring it straight back
        from the server, where it still existed. With ``origin`` (required
        for a versioned entry) the tombstone is a new version made by that
        device. Without it the tombstone is stamped no earlier than the entry
        it deletes, so a clock running behind cannot make the deletion lose
        to the value it removed.
        """
        entry = self.sections.get(section, {}).get(entry_id)
        if entry is None or is_tombstone(entry):
            return False
        versioned = self.get_entry(section, entry_id)
        if versioned is not None:
            if origin is None:
                raise ConfigSyncError(
                    f"{section}/{entry_id} is versioned: removing it needs origin=<device id>")
            self.put_entry(section, versioned.removed(origin, modified_at=time.time()))
            return True
        stamp = max(time.time(), float(entry.get("last_modified", 0)))
        self.sections[section][entry_id] = {"deleted": True, "last_modified": stamp}
        return True

    def entries(self, section: str) -> Dict[str, Dict[str, Any]]:
        """The live entries of ``section`` as stored: everything except tombstones."""
        return {entry_id: entry for entry_id, entry in self.sections.get(section, {}).items()
                if not is_tombstone(entry)}

    def values(self, section: str) -> Dict[str, Dict[str, Any]]:
        """The live values of ``section``, whichever shape they are stored in.

        A versioned entry yields its ``value``; an entry still in conflict is
        left out (see :meth:`conflicts`); a flat entry yields itself.
        """
        values: Dict[str, Dict[str, Any]] = {}
        for entry_id, entry in self.entries(section).items():
            if "vector" not in entry:
                values[entry_id] = entry
            elif isinstance(entry.get("value"), Mapping):
                values[entry_id] = dict(entry["value"])
        return values

    def get_entry(self, section: str, entry_id: str) -> Optional["SyncEntry"]:
        """The versioned entry stored for ``entry_id``; ``None`` if absent or flat."""
        from je_auto_control.utils.config_sync.versions import SyncEntry, is_versioned
        body = self.sections.get(section, {}).get(entry_id)
        if body is None or not is_versioned(body):
            return None
        return SyncEntry.from_dict(entry_id, body)

    def put_entry(self, section: str, entry: "SyncEntry") -> None:
        """Store a versioned entry under its key."""
        self.sections.setdefault(section, {})[entry.key] = entry.to_dict()

    def sync_entries(self, section: str) -> Dict[str, "SyncEntry"]:
        """Every versioned entry of ``section``, tombstones and conflicts included."""
        from je_auto_control.utils.config_sync.versions import SyncEntry, is_versioned
        return {entry_id: SyncEntry.from_dict(entry_id, body)
                for entry_id, body in self.sections.get(section, {}).items()
                if is_versioned(body)}

    def conflicts(self) -> List[Tuple[str, "SyncEntry"]]:
        """``(section, entry)`` for every entry still holding concurrent changes."""
        found: List[Tuple[str, "SyncEntry"]] = []
        for section in sorted(self.sections):
            found.extend((section, entry) for _key, entry in sorted(self.sync_entries(section).items())
                         if entry.in_conflict)
        return found

    def peer_states(self) -> Dict[str, "PeerState"]:
        """The devices taking part in this bucket, by device id."""
        from je_auto_control.utils.config_sync.versions import PeerState
        return {device: PeerState.from_dict(device, body) for device, body in self.peers.items()}


def _finite(value: Any, what: str) -> float:
    """``value`` as a finite float, or :class:`ConfigSyncError`."""
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigSyncError(f"{what} must be a number, got {value!r}") from error
    if not math.isfinite(number):
        raise ConfigSyncError(f"{what} must be finite, got {value!r}")
    return number


def _section(name: Any, section: Any) -> Dict[str, Dict[str, Any]]:
    from je_auto_control.utils.config_sync.versions import SyncEntry, is_versioned
    if not isinstance(section, Mapping):
        raise ConfigSyncError(f"section {name!r} must be a mapping")
    entries: Dict[str, Dict[str, Any]] = {}
    for entry_id, entry in section.items():
        if not isinstance(entry, Mapping):
            raise ConfigSyncError(f"entry {name!r}/{entry_id!r} must be a mapping")
        entries[str(entry_id)] = dict(entry)
        _finite(entry.get("last_modified", 0), f"{name}/{entry_id} last_modified")
        if not isinstance(entry.get("deleted", False), bool):
            raise ConfigSyncError(f"entry {name!r}/{entry_id!r} deleted must be a boolean")
        if is_versioned(entry):
            SyncEntry.from_dict(str(entry_id), entry)
    return entries


def _peers(peers: Any) -> Dict[str, Dict[str, Any]]:
    from je_auto_control.utils.config_sync.versions import PeerState
    if not isinstance(peers, Mapping):
        raise ConfigSyncError("bucket peers must be a mapping")
    return {str(device): PeerState.from_dict(str(device), body).to_dict()
            for device, body in peers.items()}


def merge_buckets(local: ConfigBucket,
                  remote: ConfigBucket,
                  *, now: Optional[float] = None,
                  tombstone_retention_s: float = TOMBSTONE_RETENTION_S,
                  ) -> Tuple[ConfigBucket, List[ConflictRecord]]:
    """Merge every section of two buckets. Returns merged + conflicts.

    Versioned entries (see :meth:`ConfigBucket.upsert`) merge by causality:
    the one made knowing the other wins, and two made apart are both kept as
    an unresolved conflict -- no clock is consulted. Their tombstones are
    never dropped here.

    Unversioned entries keep the last-write-wins rule: tombstones take part
    like any other entry, so a deletion newer than a remote copy removes it
    and an edit newer than a deletion restores it, and unversioned tombstones
    older than ``tombstone_retention_s`` (measured from ``now``, default the
    current time) are left out of the result. A versioned entry supersedes
    an unversioned copy of the same id, which is reported as dropped.
    """
    if local.user_id != remote.user_id:
        raise ConfigSyncError(
            f"user_id mismatch: local={local.user_id!r} remote={remote.user_id!r}",
        )
    merged = ConfigBucket(user_id=local.user_id, peers=_merged_peers(local, remote))
    conflicts: List[ConflictRecord] = []
    cutoff = (time.time() if now is None else now) - tombstone_retention_s
    for name in set(local.sections) | set(remote.sections):
        merged_section, found = _merge_section(
            name, local.sections.get(name, {}), remote.sections.get(name, {}))
        conflicts.extend(found)
        merged.sections[name] = _without_expired(merged_section, cutoff)
    merged.revision = max(local.revision, remote.revision) + 1
    return merged, conflicts


def _merged_peers(local: ConfigBucket, remote: ConfigBucket) -> Dict[str, Dict[str, Any]]:
    # The server's record of the peers is the shared one; local-only devices
    # are ones this machine has not announced yet.
    return {**{device: dict(body) for device, body in local.peers.items()},
            **{device: dict(body) for device, body in remote.peers.items()}}


def _merge_section(name: str, local_sec: Mapping[str, Dict[str, Any]],
                   remote_sec: Mapping[str, Dict[str, Any]],
                   ) -> Tuple[Dict[str, Dict[str, Any]], List[ConflictRecord]]:
    merged: Dict[str, Dict[str, Any]] = {}
    conflicts: List[ConflictRecord] = []
    for entry_id in set(local_sec) | set(remote_sec):
        local_entry = local_sec.get(entry_id)
        remote_entry = remote_sec.get(entry_id)
        if local_entry is None or remote_entry is None:
            present = local_entry if remote_entry is None else remote_entry
            if present is not None:
                merged[entry_id] = present
            continue
        kept, dropped, unresolved = _winner(entry_id, local_entry, remote_entry)
        merged[entry_id] = kept
        if dropped is not None:
            conflicts.append(ConflictRecord(section=name, entry_id=entry_id, dropped=dropped,
                                            kept=kept, unresolved=unresolved))
    return merged, conflicts


def _winner(entry_id: str, local_entry: Dict[str, Any], remote_entry: Dict[str, Any],
            ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], bool]:
    """``(kept, dropped, unresolved)`` for two copies of one entry."""
    local_versioned = "vector" in local_entry
    remote_versioned = "vector" in remote_entry
    if local_versioned and remote_versioned:
        return _causal_winner(entry_id, local_entry, remote_entry)
    if local_versioned != remote_versioned:
        # The unversioned copy carries no history to compare; the versioned
        # one was written by a client that had seen the bucket.
        if local_versioned:
            return local_entry, remote_entry, False
        return remote_entry, local_entry, False
    kept, dropped = _latest(local_entry, remote_entry)
    return kept, dropped, False


def _causal_winner(entry_id: str, local_entry: Dict[str, Any], remote_entry: Dict[str, Any],
                   ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], bool]:
    from je_auto_control.utils.config_sync.versions import SyncEntry, merge_entries
    decision = merge_entries(SyncEntry.from_dict(entry_id, local_entry),
                             SyncEntry.from_dict(entry_id, remote_entry))
    if decision.conflict is not None:
        return decision.entry.to_dict(), remote_entry, True
    # One side already included the other: nothing was lost, nothing to report.
    return decision.entry.to_dict(), None, False


def _latest(local_entry: Dict[str, Any], remote_entry: Dict[str, Any],
            ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """The unversioned entry that wins and the one it beat (``None`` when equal).

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
    # Only unversioned tombstones expire by age. A versioned one is collected
    # when the peers have acknowledged it, however long that takes.
    return {entry_id: entry for entry_id, entry in section.items()
            if not (is_tombstone(entry) and "vector" not in entry
                    and float(entry.get("last_modified", 0)) < cutoff)}


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


def batch_operation_id(base_revision: int, operations: Sequence["SyncOperation"]) -> str:
    """The id of the push that applies ``operations`` on top of ``base_revision``.

    Derived from the operations themselves, so the same batch retried after
    a lost reply -- or after a restart -- names the same server-side write.
    """
    digest = hashlib.sha256(str(int(base_revision)).encode("ascii"))
    for operation_id in sorted(operation.operation_id for operation in operations):
        digest.update(b"\0" + operation_id.encode("utf-8"))
    return "batch-" + digest.hexdigest()[:48]


def _apply_operation(bucket: ConfigBucket, operation: "SyncOperation",
                     conflicts: List["SyncConflict"]) -> bool:
    """Merge one operation into ``bucket``; whether the bucket changed."""
    from je_auto_control.utils.config_sync.versions import SyncConflict, merge_entries
    entry = operation.entry
    current = bucket.get_entry(operation.section, entry.key)
    if current is None:
        # No entry, or an unversioned one this change supersedes.
        bucket.put_entry(operation.section, entry)
        return True
    decision = merge_entries(current, entry)
    if decision.conflict is not None:
        conflicts.append(SyncConflict(key=entry.key, local=entry, remote=current,
                                      section=operation.section))
    if decision.entry == current:
        return False
    bucket.put_entry(operation.section, decision.entry)
    return True


def _awaits_ack(bucket: ConfigBucket, device_id: str) -> bool:
    """Whether a tombstone is still waiting for ``device_id`` to acknowledge it."""
    peer = bucket.peer_states().get(device_id)
    if peer is None:
        return True
    return any(entry.deleted and entry.deleted_revision > peer.acked_revision
               for section in bucket.sections
               for entry in bucket.sync_entries(section).values())


def _settle(bucket: ConfigBucket, device_id: str, revision: int, now: float,
            max_offline_s: Optional[float]) -> None:
    """Prepare ``bucket`` to be committed as ``revision`` by ``device_id``.

    Stamps new tombstones with the revision that first carries them, records
    that this device has merged up to it, retires peers unseen for longer
    than ``max_offline_s`` (when given), and drops the tombstones every
    remaining peer has acknowledged.
    """
    from je_auto_control.utils.config_sync.versions import PeerState, collect_tombstones
    peers = bucket.peer_states()
    peers[device_id] = PeerState(device_id, acked_revision=revision, last_seen=now)
    if max_offline_s is not None:
        peers = {device: (replace(peer, retired=True)
                          if device != device_id and peer.last_seen < now - max_offline_s else peer)
                 for device, peer in peers.items()}
    bucket.peers = {device: peer.to_dict() for device, peer in peers.items()}
    for section in list(bucket.sections):
        versioned = _stamped(bucket.sync_entries(section), revision)
        kept = collect_tombstones(versioned, peers.values())
        flat = {key: body for key, body in bucket.sections[section].items() if key not in versioned}
        bucket.sections[section] = {**flat, **{key: entry.to_dict() for key, entry in kept.items()}}


def _stamped(entries: Mapping[str, "SyncEntry"], revision: int) -> Dict[str, "SyncEntry"]:
    """``entries`` with each new tombstone marked as first carried by ``revision``."""
    return {key: (replace(entry, deleted_revision=revision)
                  if entry.deleted and not entry.deleted_revision else entry)
            for key, entry in entries.items()}


class ConfigSyncClient:
    """Stdlib HTTP client for the signaling server's ``/config`` endpoints.

    Methods are intentionally small and synchronous — the GUI wraps
    them in QThread workers when wiring up periodic sync.
    """

    def __init__(self, server_url: str, *,
                 user_id: str, secret: Optional[str] = None,
                 timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        if not server_url:
            raise ConfigSyncError("server_url is required")
        if not user_id:
            raise ConfigSyncError("user_id is required")
        self._server_url = server_url.rstrip("/")
        self._user_id = user_id
        self._secret = secret
        self._timeout = float(timeout_s)

    @property
    def user_id(self) -> str:
        """The account this client syncs."""
        return self._user_id

    @property
    def server_url(self) -> str:
        """The server this client talks to, without a trailing slash."""
        return self._server_url

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
            raise ConfigSyncConflict(
                f"config sync {method}: the server is at another revision",
                _conflict_revision(response.get("text")))
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
        revision the first attempt produced instead of a conflict.
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
             ) -> Tuple[ConfigBucket, List[ConflictRecord]]:
        """Bidirectional sync: fetch, merge, push on top of what was fetched.

        When another machine pushes between the fetch and the push the
        server refuses the write, and this fetches and merges again -- up to
        ``max_attempts`` times, then :class:`ConfigSyncConflict`. The
        returned bucket's ``revision`` is the one the server committed.
        """
        for _attempt in range(max(1, int(max_attempts))):
            remote = self.fetch() or ConfigBucket(user_id=self._user_id)
            merged, conflicts = merge_buckets(local, remote)
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
        when the bucket holds a deletion this device has not acknowledged.

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
            changed = [_apply_operation(merged, operation, conflicts) for operation in operations]
            if not any(changed) and not _awaits_ack(remote, device_id):
                return SyncResult(bucket=remote, revision=remote.revision, conflicts=conflicts)
            _settle(merged, device_id, remote.revision + 1, stamp, max_offline_s)
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


def _conflict_revision(text: Any) -> Optional[int]:
    """The current revision a 409 reply names, when it names one."""
    try:
        revision = json.loads(text or "").get("revision")
    except (json.JSONDecodeError, RecursionError, AttributeError, TypeError):
        return None
    return revision if isinstance(revision, int) and not isinstance(revision, bool) else None


__all__ = [
    "ConfigBucket", "ConflictRecord", "ConfigSyncClient", "ConfigSyncConflict",
    "ConfigSyncError", "DEFAULT_SYNC_ATTEMPTS", "FullResyncRequired", "SyncResult",
    "TOMBSTONE_RETENTION_S", "WIRE_VERSION", "batch_operation_id",
    "is_tombstone", "merge_buckets", "new_operation_id",
]
