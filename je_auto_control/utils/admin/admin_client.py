"""Headless multi-host admin console.

Talks to N AutoControl REST instances in parallel using stdlib
``urllib.request`` + a thread pool (no extra deps). The address book is
persisted as JSON under ``~/.je_auto_control/admin_hosts.json`` so the
GUI can survive restarts. Tokens are kept in the same file — the user
must protect it like an SSH private key (the file is written with mode
``0o600`` on POSIX; on Windows it inherits the user's profile ACL).
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_PATH_RELATIVE = ".je_auto_control/admin_hosts.json"
_DEFAULT_TIMEOUT = 3.0
_DEFAULT_MAX_PARALLEL = 8


def default_admin_hosts_path() -> Path:
    return Path(os.path.expanduser("~")) / _DEFAULT_PATH_RELATIVE


@dataclass
class AdminHost:
    """A single AutoControl REST endpoint registered with the console."""

    label: str
    base_url: str
    token: str
    tags: List[str] = field(default_factory=list)


@dataclass
class HostStatus:
    """Snapshot of one host after a poll round."""

    label: str
    base_url: str
    healthy: bool
    latency_ms: float
    error: Optional[str] = None
    sessions: Optional[Dict[str, Any]] = None
    job_count: Optional[int] = None


class AdminConsoleClient:
    """In-memory address book + parallel REST poller / broadcaster."""

    def __init__(self, *, persist_path: Optional[Path] = None,
                 max_parallel: int = _DEFAULT_MAX_PARALLEL,
                 timeout_s: float = _DEFAULT_TIMEOUT) -> None:
        self._path = Path(persist_path) if persist_path is not None \
            else default_admin_hosts_path()
        self._max_parallel = max(1, int(max_parallel))
        self._timeout = float(timeout_s)
        self._lock = threading.Lock()
        self._hosts: Dict[str, AdminHost] = {}
        self._load()

    @property
    def persist_path(self) -> Path:
        return self._path

    def list_hosts(self) -> List[AdminHost]:
        with self._lock:
            return list(self._hosts.values())

    def add_host(self, label: str, base_url: str, token: str,
                 *, tags: Optional[List[str]] = None) -> AdminHost:
        if not label or not base_url or not token:
            raise ValueError("label, base_url, and token are required")
        host = AdminHost(
            label=label.strip(), base_url=base_url.rstrip("/"),
            token=token.strip(), tags=list(tags or []),
        )
        with self._lock:
            self._hosts[host.label] = host
        self._save()
        return host

    def remove_host(self, label: str) -> bool:
        with self._lock:
            removed = self._hosts.pop(label, None) is not None
        if removed:
            self._save()
        return removed

    def poll_all(self, *, labels: Optional[List[str]] = None) -> List[HostStatus]:
        targets = self._resolve_targets(labels)
        if not targets:
            return []
        with ThreadPoolExecutor(max_workers=self._max_parallel) as pool:
            return list(pool.map(self._poll_one, targets))

    def broadcast_execute(self, actions: List[Any],
                          *, labels: Optional[List[str]] = None,
                          ) -> List[Dict[str, Any]]:
        targets = self._resolve_targets(labels)
        if not targets:
            return []
        with ThreadPoolExecutor(max_workers=self._max_parallel) as pool:
            return list(pool.map(
                lambda host: self._execute_one(host, actions), targets,
            ))

    def _resolve_targets(self, labels: Optional[List[str]]) -> List[AdminHost]:
        if not labels:
            return self.list_hosts()
        with self._lock:
            return [self._hosts[label] for label in labels
                    if label in self._hosts]

    def _poll_one(self, host: AdminHost) -> HostStatus:
        # Probe an authenticated endpoint — that way a bad token shows as
        # unhealthy, not as "reachable but useless". /sessions is cheap.
        start = time.monotonic()
        try:
            sessions = self._http_get(host, "/sessions")
        except (OSError, ValueError, TimeoutError) as error:  # urllib.error.URLError is an OSError subclass; keep TimeoutError for Python 3.10 where it isn't (NOSONAR python:S5713)
            return HostStatus(
                label=host.label, base_url=host.base_url, healthy=False,
                latency_ms=(time.monotonic() - start) * 1000.0,
                error=str(error),
            )
        latency = (time.monotonic() - start) * 1000.0
        jobs = self._safe_get(host, "/jobs")
        return HostStatus(
            label=host.label, base_url=host.base_url, healthy=True,
            latency_ms=latency, sessions=sessions,
            job_count=len(jobs.get("jobs", [])) if isinstance(jobs, dict) else None,
        )

    def _safe_get(self, host: AdminHost, path: str) -> Optional[Dict[str, Any]]:
        try:
            return self._http_get(host, path)
        except (OSError, ValueError, TimeoutError) as error:  # urllib.error.URLError is an OSError subclass; keep TimeoutError for Python 3.10 where it isn't (NOSONAR python:S5713)
            autocontrol_logger.warning(
                "admin: %s GET %s failed: %r", host.label, path, error,
            )
            return None

    def _execute_one(self, host: AdminHost,
                     actions: List[Any]) -> Dict[str, Any]:
        try:
            payload = self._http_post(host, "/execute", {"actions": actions})
            return {"label": host.label, "ok": True, "result": payload}
        except (OSError, ValueError, TimeoutError) as error:  # urllib.error.URLError is an OSError subclass; keep TimeoutError for Python 3.10 where it isn't (NOSONAR python:S5713)
            return {"label": host.label, "ok": False, "error": str(error)}

    def _http_get(self, host: AdminHost, path: str) -> Dict[str, Any]:
        return self._http_request(host, path, method="GET", body=None)

    def _http_post(self, host: AdminHost, path: str,
                   body: Dict[str, Any]) -> Dict[str, Any]:
        return self._http_request(host, path, method="POST", body=body)

    def _http_request(self, host: AdminHost, path: str, *,
                      method: str, body: Optional[Dict[str, Any]],
                      ) -> Dict[str, Any]:
        url = f"{host.base_url}{path}"
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"unsupported URL scheme: {url}")
        headers = {"Authorization": f"Bearer {host.token}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, data=data, headers=headers, method=method,
        )
        with urllib.request.urlopen(  # nosec B310  # reason: scheme validated above to http(s) only
                request, timeout=self._timeout,
        ) as response:
            raw = response.read()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            autocontrol_logger.warning("admin: load %s failed: %r",
                                       self._path, error)
            return
        with self._lock:
            self._hosts = {
                entry["label"]: AdminHost(**entry)
                for entry in payload.get("hosts", [])
                if isinstance(entry, dict) and entry.get("label")
            }

    def _save(self) -> None:
        with self._lock:
            payload = {"hosts": [asdict(h) for h in self._hosts.values()]}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            if os.name == "posix":
                os.chmod(self._path, 0o600)
        except OSError as error:
            autocontrol_logger.warning("admin: save %s failed: %r",
                                       self._path, error)


_default_console: Optional[AdminConsoleClient] = None
_default_lock = threading.Lock()


def default_admin_console() -> AdminConsoleClient:
    """Process-wide singleton on the default address-book path."""
    global _default_console
    with _default_lock:
        if _default_console is None:
            _default_console = AdminConsoleClient()
        return _default_console


__all__ = [
    "AdminConsoleClient", "AdminHost", "HostStatus",
    "default_admin_console", "default_admin_hosts_path",
]
