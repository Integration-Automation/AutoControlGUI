"""HTTP client + deterministic merge for the config-sync bucket."""
from __future__ import annotations

import json
import math
import time
import urllib.parse
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

_DEFAULT_TIMEOUT_S = 5.0
#: The ``/config`` wire format: a PUT is an envelope naming the revision it
#: was built on and an operation id, and is refused when that revision is stale.
WIRE_VERSION = 2
#: How often :meth:`ConfigSyncClient.sync` fetches, merges and pushes again
#: after losing a race to another machine before it gives up.
DEFAULT_SYNC_ATTEMPTS = 4

#: How long a deletion is remembered. A tombstone purged before every machine
#: has synced lets a machine that still holds the entry bring it back, so this
#: bounds how long a machine may stay offline without that happening.
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


def new_operation_id() -> str:
    """A fresh id for one push; reuse it when retrying that same push."""
    return uuid.uuid4().hex


@dataclass
class ConflictRecord:
    """One entry that lost a last-modified race during the merge."""
    section: str
    entry_id: str
    dropped: Dict[str, Any]
    kept: Dict[str, Any]


@dataclass
class ConfigBucket:
    """JSON-shaped bucket persisted on the sync server.

    Each section maps an opaque ``entry_id`` to a dict that must carry
    a ``last_modified`` epoch timestamp. Unknown sections are passed
    through untouched so callers can extend the schema without
    touching the syncer.

    A removed entry stays in ``sections`` as a tombstone
    (``{"deleted": True, "last_modified": ...}``) so the deletion wins the
    merge against an older copy on another machine instead of being undone
    by it; read entries through :meth:`entries`, which leaves tombstones out.
    """
    user_id: str
    sections: Dict[str, Dict[str, Dict[str, Any]]] = field(
        default_factory=dict,
    )
    revision: int = 0

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
        )

    def upsert(self, section: str, entry_id: str,
               entry: Mapping[str, Any]) -> None:
        """Add or replace an entry, stamping it with the current time.

        A ``last_modified`` already in ``entry`` is kept, so drop it when
        editing an entry read back from a bucket -- otherwise the edit keeps
        its old stamp and loses the merge to any newer remote copy.
        """
        body = dict(entry)
        body["last_modified"] = float(body.get("last_modified", time.time()))
        self.sections.setdefault(section, {})[entry_id] = body

    def remove(self, section: str, entry_id: str) -> bool:
        """Replace a live entry with a tombstone; False when there was none.

        Dropping the entry outright let the next sync bring it straight back
        from the server, where it still existed. The tombstone is stamped no
        earlier than the entry it deletes, so a clock running behind cannot
        make the deletion lose to the value it removed.
        """
        entry = self.sections.get(section, {}).get(entry_id)
        if entry is None or is_tombstone(entry):
            return False
        stamp = max(time.time(), float(entry.get("last_modified", 0)))
        self.sections[section][entry_id] = {"deleted": True, "last_modified": stamp}
        return True

    def entries(self, section: str) -> Dict[str, Dict[str, Any]]:
        """The live entries of ``section``: everything except tombstones."""
        return {entry_id: entry for entry_id, entry in self.sections.get(section, {}).items()
                if not is_tombstone(entry)}


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
    return entries


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
        merged_section: Dict[str, Dict[str, Any]] = {}
        local_sec = local.sections.get(name, {})
        remote_sec = remote.sections.get(name, {})
        ids = set(local_sec) | set(remote_sec)
        for entry_id in ids:
            local_entry = local_sec.get(entry_id)
            remote_entry = remote_sec.get(entry_id)
            if local_entry is None:
                if remote_entry is not None:
                    merged_section[entry_id] = remote_entry
                continue
            if remote_entry is None:
                merged_section[entry_id] = local_entry
                continue
            kept, dropped = _winner(local_entry, remote_entry)
            merged_section[entry_id] = kept
            if dropped is not None:
                conflicts.append(ConflictRecord(
                    section=name, entry_id=entry_id, dropped=dropped, kept=kept,
                ))
        merged.sections[name] = _without_expired(
            merged_section, (time.time() if now is None else now) - tombstone_retention_s)
    merged.revision = max(local.revision, remote.revision) + 1
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
                 timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        if not server_url:
            raise ConfigSyncError("server_url is required")
        if not user_id:
            raise ConfigSyncError("user_id is required")
        self._server_url = server_url.rstrip("/")
        self._user_id = user_id
        self._secret = secret
        self._timeout = float(timeout_s)

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


def _conflict_revision(text: Any) -> Optional[int]:
    """The current revision a 409 reply names, when it names one."""
    try:
        revision = json.loads(text or "").get("revision")
    except (json.JSONDecodeError, RecursionError, AttributeError, TypeError):
        return None
    return revision if isinstance(revision, int) and not isinstance(revision, bool) else None


__all__ = [
    "ConfigBucket", "ConflictRecord", "ConfigSyncClient", "ConfigSyncConflict",
    "ConfigSyncError", "DEFAULT_SYNC_ATTEMPTS", "TOMBSTONE_RETENTION_S", "WIRE_VERSION",
    "is_tombstone", "merge_buckets", "new_operation_id",
]
