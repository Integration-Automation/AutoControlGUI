"""Prometheus exposition for the REST server.

Tracks per-(method, path, status) request counts and a few process gauges
so a Grafana scraper can render usage / health graphs without parsing
the audit log. Format follows the text exposition spec — one line per
metric sample, ``# HELP`` and ``# TYPE`` headers per family.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Tuple


class RestMetrics:
    """Thread-safe counters + gauges, formatted on demand."""

    def __init__(self) -> None:
        self._started_at = time.time()
        self._lock = threading.Lock()
        self._requests: Dict[Tuple[str, str, int], int] = {}
        self._failed_auth: int = 0

    def record_request(self, method: str, path: str, status: int) -> None:
        key = (method, path, int(status))
        with self._lock:
            self._requests[key] = self._requests.get(key, 0) + 1

    def record_failed_auth(self) -> None:
        with self._lock:
            self._failed_auth += 1

    def render(self, *, audit_row_count: int = 0,
               active_sessions: int = 0,
               scheduler_jobs: int = 0) -> str:
        uptime = time.time() - self._started_at
        with self._lock:
            requests_snapshot = dict(self._requests)
            failed_auth = self._failed_auth
        lines = [
            "# HELP autocontrol_rest_uptime_seconds Process uptime in seconds.",
            "# TYPE autocontrol_rest_uptime_seconds gauge",
            f"autocontrol_rest_uptime_seconds {uptime:.3f}",
            "# HELP autocontrol_rest_failed_auth_total Total failed bearer auth attempts.",
            "# TYPE autocontrol_rest_failed_auth_total counter",
            f"autocontrol_rest_failed_auth_total {failed_auth}",
            "# HELP autocontrol_rest_audit_rows Audit log row count.",
            "# TYPE autocontrol_rest_audit_rows gauge",
            f"autocontrol_rest_audit_rows {int(audit_row_count)}",
            "# HELP autocontrol_active_sessions Remote desktop active session count.",
            "# TYPE autocontrol_active_sessions gauge",
            f"autocontrol_active_sessions {int(active_sessions)}",
            "# HELP autocontrol_scheduler_jobs Scheduler job count.",
            "# TYPE autocontrol_scheduler_jobs gauge",
            f"autocontrol_scheduler_jobs {int(scheduler_jobs)}",
            "# HELP autocontrol_rest_requests_total HTTP requests by method/path/status.",
            "# TYPE autocontrol_rest_requests_total counter",
        ]
        for (method, path, status), count in sorted(requests_snapshot.items()):
            labels = (
                f'method="{_escape(method)}",'
                f'path="{_escape(path)}",'
                f'status="{int(status)}"'
            )
            lines.append(f"autocontrol_rest_requests_total{{{labels}}} {count}")
        lines.append("")
        return "\n".join(lines)


def _escape(value: str) -> str:
    """Escape a label value per Prometheus exposition rules."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


__all__ = ["RestMetrics"]
