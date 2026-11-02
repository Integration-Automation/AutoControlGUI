"""Expire settled DAG records while retaining unresolved input and referenced recovery evidence."""
from __future__ import annotations

import json
from typing import Any

from je_auto_control.utils.agent_runtime.models import TERMINAL
from je_auto_control.utils.agent_runtime.policy import owns_task

_RELATED = """
WITH RECURSIVE related(id) AS (
 SELECT id FROM agent_tasks WHERE agent_dag_ref(spec,'options.dag_batch.batch_id')=:batch
 UNION SELECT task_id FROM agent_dag_local_tasks WHERE batch_id=:batch
 UNION SELECT task_id FROM agent_dag_adoptions WHERE batch_id=:batch
 UNION SELECT source_task FROM agent_dag_adoptions WHERE batch_id=:batch
 UNION SELECT agent_dag_ref(receipt,'task_id') FROM agent_dag_nodes WHERE batch_id=:batch
 UNION SELECT r.task_id FROM agent_task_recoveries r JOIN related p ON r.source_task=p.id
)
"""


def protects_task(store: Any, task_id: str) -> bool:
    """Keep referenced tasks and every recovery successor while their local batch is retained."""
    with store.connection() as connection:
        connection.create_function("agent_dag_ref", 2, _reference)
        row = connection.execute("""
            WITH RECURSIVE lineage(id) AS (
             SELECT ? UNION SELECT r.source_task FROM agent_task_recoveries r JOIN lineage l ON r.task_id=l.id
            )
            SELECT 1 FROM lineage l WHERE
             EXISTS (SELECT 1 FROM agent_tasks t JOIN agent_dag_batches b
                     ON b.id=agent_dag_ref(t.spec,'options.dag_batch.batch_id') WHERE t.id=l.id)
             OR EXISTS (SELECT 1 FROM agent_dag_local_tasks a WHERE a.task_id=l.id)
             OR EXISTS (SELECT 1 FROM agent_dag_adoptions a WHERE a.task_id=l.id OR a.source_task=l.id)
             OR EXISTS (SELECT 1 FROM agent_dag_nodes n WHERE agent_dag_ref(n.receipt,'task_id')=l.id)
            LIMIT 1
            """, (task_id,)).fetchone()
    return row is not None


def prune_batches(runtime: Any, cutoff: float, identity: Any) -> dict:
    """Collect up to one thousand visible settled batches; unresolved work has no automatic expiry."""
    with runtime.store.connection() as connection:
        rows = connection.execute("SELECT id,owner FROM agent_dag_batches WHERE updated<? "
                                  "AND state IN ('registered','succeeded') ORDER BY updated LIMIT 1000",
                                  (cutoff,)).fetchall()
    deleted, deliveries = [], 0
    for row in rows:
        if not owns_task(json.loads(row["owner"]), identity):
            continue
        # pylint: disable-next=protected-access  # reason: use the same lock as begin/claim/continuation/admission
        with runtime._lock("dag:" + row["id"]):
            result = _expire(runtime, row["id"], cutoff)
        if result is not None:
            deleted.append(row["id"])
            deliveries += result
    if identity is None or identity.role == "admin":
        deliveries += _orphan_deliveries(runtime.store, cutoff)
    return {"deleted_batches": deleted, "deleted_dag_deliveries": deliveries}


def _expire(runtime: Any, identifier: str, cutoff: float) -> int | None:
    with runtime.store.connection(write=True) as connection:
        connection.create_function("agent_dag_ref", 2, _reference)
        batch = connection.execute("SELECT * FROM agent_dag_batches WHERE id=? AND updated<? "
                                   "AND state IN ('registered','succeeded')", (identifier, cutoff)).fetchone()
        if batch is None or not _settled(runtime, connection, batch):
            return None
        if _has_queue(connection):
            if connection.execute("SELECT 1 FROM work_items WHERE queue='agent_dag' AND reference=? "
                                  "AND (status NOT IN ('success','failed') OR updated>=?) LIMIT 1",
                                  (identifier, cutoff)).fetchone():
                return None
            count = connection.execute("DELETE FROM work_items WHERE queue='agent_dag' AND reference=?",
                                       (identifier,)).rowcount
        else:
            count = 0
        connection.execute("DELETE FROM agent_dag_batches WHERE id=?", (identifier,))
    return count


def _settled(runtime: Any, connection: Any, batch: Any) -> bool:
    rows = connection.execute(
        _RELATED +  # nosec B608  # reason: constant SQL fragments only; batch identity is a bound parameter
        "SELECT t.id,t.state FROM agent_tasks t JOIN related r ON t.id=r.id",
                              {"batch": batch["id"]}).fetchall()
    if batch["state"] == "registered" and rows:
        return False
    # pylint: disable-next=protected-access  # reason: do not remove a live admission/actor gate or in-flight dispatch
    if any(row["state"] not in TERMINAL or row["id"] in runtime._leases or row["id"] in runtime._executing
           for row in rows):
        return False
    phase = "pending" if batch["state"] == "registered" else "confirmed"
    if connection.execute("SELECT 1 FROM agent_dag_nodes WHERE batch_id=? AND phase!=? LIMIT 1",
                          (batch["id"], phase)).fetchone():
        return False
    return connection.execute(
        _RELATED +  # nosec B608  # reason: constant SQL fragments only; batch identity is a bound parameter
        "SELECT 1 FROM related r WHERE "
        "EXISTS (SELECT 1 FROM agent_control c WHERE c.owner=r.id) OR "
        "EXISTS (SELECT 1 FROM agent_actions a WHERE a.task_id=r.id "
        "AND a.status IN ('prepared','dispatched','uncertain')) LIMIT 1", {"batch": batch["id"]}).fetchone() is None


def _has_queue(connection: Any) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE name='work_items'").fetchone() is not None


def _orphan_deliveries(store: Any, cutoff: float) -> int:
    with store.connection(write=True) as connection:
        if not _has_queue(connection):
            return 0
        return connection.execute("DELETE FROM work_items WHERE queue='agent_dag' "
            "AND id IN (SELECT id FROM work_items WHERE queue='agent_dag' "
            "AND status IN ('success','failed') AND updated<? AND NOT EXISTS "
            "(SELECT 1 FROM agent_dag_batches WHERE id=work_items.reference) ORDER BY updated LIMIT 1000)",
            (cutoff,)).rowcount


def _reference(encoded: str, path: str) -> str | None:
    """Read only string identities without requiring the optional SQLite JSON extension."""
    value = json.loads(encoded)
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, str) else None
