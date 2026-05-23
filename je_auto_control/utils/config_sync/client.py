"""HTTP client + deterministic merge for the config-sync bucket."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

_DEFAULT_TIMEOUT_S = 5.0


class ConfigSyncError(RuntimeError):
    """Raised on network errors or schema validation failures."""


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
        return cls(
            user_id=body["user_id"],
            sections={
                str(name): {str(eid): dict(entry)
                            for eid, entry in (sec or {}).items()}
                for name, sec in sections.items()
            },
            revision=int(body.get("revision", 0)),
        )

    def upsert(self, section: str, entry_id: str,
               entry: Mapping[str, Any]) -> None:
        """Add or replace an entry, stamping it with the current time."""
        body = dict(entry)
        body["last_modified"] = float(body.get("last_modified", time.time()))
        self.sections.setdefault(section, {})[entry_id] = body

    def remove(self, section: str, entry_id: str) -> bool:
        sec = self.sections.get(section)
        if not sec:
            return False
        return sec.pop(entry_id, None) is not None


def merge_buckets(local: ConfigBucket,
                  remote: ConfigBucket,
                  ) -> Tuple[ConfigBucket, List[ConflictRecord]]:
    """Last-write-wins merge across every section. Returns merged + conflicts."""
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
                merged_section[entry_id] = remote_entry
                continue
            if remote_entry is None:
                merged_section[entry_id] = local_entry
                continue
            local_ts = float(local_entry.get("last_modified", 0))
            remote_ts = float(remote_entry.get("last_modified", 0))
            if remote_ts > local_ts:
                merged_section[entry_id] = remote_entry
                conflicts.append(ConflictRecord(
                    section=name, entry_id=entry_id,
                    dropped=local_entry, kept=remote_entry,
                ))
            elif local_ts > remote_ts:
                merged_section[entry_id] = local_entry
                conflicts.append(ConflictRecord(
                    section=name, entry_id=entry_id,
                    dropped=remote_entry, kept=local_entry,
                ))
            else:
                merged_section[entry_id] = local_entry  # tie — local wins
        merged.sections[name] = merged_section
    merged.revision = max(local.revision, remote.revision) + 1
    return merged, conflicts


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
        headers = {"Content-Type": "application/json"}
        if self._secret:
            headers["X-Signaling-Secret"] = self._secret
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self._endpoint(), data=data, method=method, headers=headers,
        )
        try:
            with urllib.request.urlopen(  # nosec B310  # NOSONAR python:S5332  # reason: scheme allowlisted by caller config
                    request, timeout=self._timeout,
            ) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise ConfigSyncError(
                f"config sync {method} returned HTTP {error.code}",
            ) from error
        except urllib.error.URLError as error:
            raise ConfigSyncError(
                f"config sync {method} failed: {error.reason}",
            ) from error
        if not payload:
            return {}
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConfigSyncError("config sync: invalid JSON reply") from error

    def fetch(self) -> Optional[ConfigBucket]:
        """GET the bucket from the server, or ``None`` when none exists."""
        body = self._request("GET")
        if body is None:
            return None
        return ConfigBucket.from_dict(body)

    def push(self, bucket: ConfigBucket) -> None:
        """PUT the bucket to the server, replacing whatever's there."""
        if bucket.user_id != self._user_id:
            raise ConfigSyncError(
                f"bucket user_id={bucket.user_id!r} mismatches client user_id"
                f"={self._user_id!r}",
            )
        self._request("PUT", body=bucket.to_dict())

    def sync(self, local: ConfigBucket
             ) -> Tuple[ConfigBucket, List[ConflictRecord]]:
        """One-shot bidirectional sync: fetch, merge, push the result."""
        remote = self.fetch() or ConfigBucket(user_id=self._user_id)
        merged, conflicts = merge_buckets(local, remote)
        self.push(merged)
        return merged, conflicts


__all__ = [
    "ConfigBucket", "ConflictRecord", "ConfigSyncClient",
    "ConfigSyncError", "merge_buckets",
]
