"""Renewed trigger lineages share accepted event tombstones and outstanding-task limits."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def lineage(connection: Any, identifier: str) -> str | None:
    """Find the durable family even after an ancestor binding has been removed."""
    row = connection.execute("SELECT lineage FROM agent_trigger_authorizations "
                             "WHERE trigger_id=? OR source_trigger=? LIMIT 1", (identifier, identifier)).fetchone()
    return row[0] if row is not None else None


def require_current(connection: Any, identifier: str) -> None:
    """A retired binding cannot be reenabled or produce more work, even after child removal."""
    if connection.execute("SELECT 1 FROM agent_trigger_authorizations WHERE source_trigger=?",
                          (identifier,)).fetchone() is not None:
        raise AgentTaskError("trigger has a reviewed replacement; use that registration")


def event_state(connection: Any, identifier: str, event_hash: str) -> tuple[dict | None, int]:
    """Read deduplication and pending count from the same original or renewed event namespace."""
    family = lineage(connection, identifier)
    if family is None:
        previous = connection.execute("SELECT *,trigger_id AS origin_trigger FROM agent_trigger_events "
                                      "WHERE trigger_id=? AND event_hash=?", (identifier, event_hash)).fetchone()
        pending = connection.execute("SELECT COUNT(*) FROM agent_trigger_events e JOIN agent_tasks t ON t.id=e.task_id "
            "WHERE e.trigger_id=? AND t.state NOT IN ('succeeded','failed','cancelled','timed_out')",
            (identifier,)).fetchone()[0]
    else:
        previous = connection.execute("SELECT * FROM agent_trigger_event_history WHERE lineage=? AND event_hash=?",
                                      (family, event_hash)).fetchone()
        pending = connection.execute("SELECT COUNT(DISTINCT e.task_id) FROM agent_trigger_event_history e "
            "JOIN agent_tasks t ON t.id=e.task_id WHERE e.lineage=? "
            "AND t.state NOT IN ('succeeded','failed','cancelled','timed_out')", (family,)).fetchone()[0]
    return dict(previous) if previous is not None else None, pending


def bind_event(connection: Any, event: tuple[str, str, str], task_id: str, now: float) -> None:
    """Bind lineage deduplication in the same transaction as task/local event acceptance."""
    identifier, event_hash, payload_hash = event
    family = lineage(connection, identifier)
    if family is not None:
        require_current(connection, identifier)
        connection.execute("INSERT INTO agent_trigger_event_history VALUES (?,?,?,?,?,?)",
                           (family, event_hash, payload_hash, task_id, identifier, now))


def seed_history(connection: Any, source: str) -> str:
    """Retain the first binding's accepted events before its template can be retired or removed."""
    family = lineage(connection, source) or source
    connection.execute("INSERT OR IGNORE INTO agent_trigger_event_history "
        "SELECT ?,event_hash,payload_hash,task_id,trigger_id,created FROM agent_trigger_events WHERE trigger_id=?",
        (family, source))
    return family


def snapshot_events(connection: Any, identifier: str) -> tuple[str, int]:
    """Stream accepted identities into a bounded digest; do not expose payloads or copy task results."""
    family = lineage(connection, identifier)
    if family is None:
        rows = connection.execute("SELECT event_hash,payload_hash,task_id,trigger_id,created FROM agent_trigger_events "
                                  "WHERE trigger_id=? ORDER BY event_hash", (identifier,))
    else:
        rows = connection.execute("SELECT event_hash,payload_hash,task_id,origin_trigger,created "
                                  "FROM agent_trigger_event_history WHERE lineage=? ORDER BY event_hash", (family,))
    digest, count = hashlib.sha256(), 0
    for row in rows:
        digest.update(json.dumps(list(row), separators=(",", ":")).encode() + b"\n")
        count += 1
    return digest.hexdigest(), count


def clear_unused_history(connection: Any, identifier: str) -> None:
    """Keep proof while any family template remains; remove it after explicit removal of the whole family."""
    family = lineage(connection, identifier)
    if family is None:
        return
    exists = connection.execute("SELECT 1 FROM agent_triggers WHERE id=? OR id IN "
        "(SELECT trigger_id FROM agent_trigger_authorizations WHERE lineage=?) OR id IN "
        "(SELECT source_trigger FROM agent_trigger_authorizations WHERE lineage=?) LIMIT 1",
        (family, family, family)).fetchone()
    if exists is None:
        connection.execute("DELETE FROM agent_trigger_event_history WHERE lineage=?", (family,))
        connection.execute("DELETE FROM agent_trigger_authorizations WHERE lineage=?", (family,))
