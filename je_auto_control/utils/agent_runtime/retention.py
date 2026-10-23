"""Thirty-day cleanup of stopped tasks and exclusively owned runtime artifacts."""
from __future__ import annotations

import time
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.policy import owns_task
from je_auto_control.utils.rbac.authorization import current_authorization


def prune_tasks(runtime: Any, keep_days: int = 30) -> dict[str, Any]:
    """Prune at most one thousand expired terminal tasks visible to this caller per sweep."""
    if isinstance(keep_days, bool) or not isinstance(keep_days, int) or not 1 <= keep_days <= 3650:
        raise AgentTaskError("retention must be between one and 3650 days")
    identity = current_authorization()
    if identity is None or identity.role == "admin":
        _orphan_deliveries(runtime.store)
    with runtime.store.connection() as connection:
        identifiers = [row[0] for row in connection.execute(
            "SELECT id FROM agent_tasks WHERE state IN ('succeeded','failed','cancelled','timed_out') "
            "AND updated<? ORDER BY updated LIMIT 1000", (time.time() - keep_days * 86400,))]
    deleted = []
    for task_id in identifiers:
        with runtime._lock(task_id):
            row = runtime.store.get(task_id)
            if not owns_task(row["owner"], identity):
                continue
            if task_id in runtime._leases:
                continue
            runtime.evidence.remove(task_id)
            _remove_metadata(runtime.store, task_id)
            runtime._tokens.pop(task_id, None)
            runtime._stop_final.pop(task_id, None)
            runtime._observations.pop(task_id, None)
            deleted.append(task_id)
    return {"deleted": deleted, "keep_days": keep_days}


def _remove_metadata(store: Any, task_id: str) -> None:
    with store.connection(write=True) as connection:
        connection.execute("DELETE FROM agent_reviews WHERE task_id=?", (task_id,))
        connection.execute("DELETE FROM agent_actions WHERE task_id=?", (task_id,))
        connection.execute("DELETE FROM agent_tasks WHERE id=?", (task_id,))
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='work_items'").fetchone():
            connection.execute("DELETE FROM work_items WHERE queue='agent_runtime' AND reference=? "
                               "AND status!='in_progress'", (task_id,))


def _orphan_deliveries(store: Any) -> None:
    with store.connection(write=True) as connection:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='work_items'").fetchone():
            connection.execute("DELETE FROM work_items WHERE queue='agent_runtime' AND status!='in_progress' "
                               "AND NOT EXISTS (SELECT 1 FROM agent_tasks WHERE id=work_items.reference)")
