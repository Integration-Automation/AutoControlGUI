"""Destination delivery generations bind durable import intents to exact existing WorkQueue claims."""
from __future__ import annotations

import json
import time
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import _deadline

QUEUE = 'agent_transfer_import'
FINAL = frozenset({'published', 'requires_review', 'cancelled', 'expired'})


def _delivery_data(data: Any, identifier: str, generation: int) -> bool:
    if not isinstance(data, dict) or set(data) != {'import_id', 'generation'}:
        return False
    if isinstance(data['generation'], bool) or not isinstance(data['generation'], int):
        return False
    return data['import_id'] == identifier and data['generation'] == generation


def _insert_queue(connection: Any, identifier: str, generation: int) -> int:
    cursor = connection.execute('INSERT INTO work_items (queue,reference,data,status,updated) VALUES (?,?,?,?,?)',
        (QUEUE, identifier, json.dumps({'import_id': identifier, 'generation': generation}), 'new', time.time()))
    if cursor.lastrowid is None:
        raise AgentTaskError('destination delivery queue insertion did not establish an identity')
    return cursor.lastrowid


def _undispatched(row: Any, queue: Any) -> bool:
    # An explicitly queued, never-claimed inspection retains its prior publication for read-only verification.
    if row['state'] != 'queued' or row['claim'] != 0:
        return False
    if queue is None or queue['status'] != 'new' or queue['claim'] != 0:
        return False
    try:
        data = json.loads(queue['data'])
    except (ValueError, TypeError, RecursionError):
        return False
    return queue['reference'] == row['id'] and _delivery_data(data, row['id'], row['generation'])


class TransferImportLedger:
    """Only this runtime's writer changes delivery state; obsolete claims never authorize further effects."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def initialize(self, connection: Any) -> None:
        """Create fixed import metadata without committing the owning runtime transaction."""
        connection.execute('CREATE TABLE IF NOT EXISTS agent_transfer_deliveries ('
                           'id TEXT PRIMARY KEY,generation INTEGER NOT NULL,queue_id INTEGER NOT NULL,'
                           'claim INTEGER NOT NULL,state TEXT NOT NULL,publication TEXT NOT NULL,'
                           'files_directory TEXT NOT NULL,updated REAL NOT NULL,ceilings TEXT NOT NULL DEFAULT \'[]\')')
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(agent_transfer_deliveries)')}
        if 'ceilings' not in columns:
            connection.execute("ALTER TABLE agent_transfer_deliveries ADD COLUMN ceilings TEXT NOT NULL DEFAULT '[]'")

    def enqueue(self, connection: Any, identifier: str) -> None:
        """Persist the queue item in the same writer as the original approved import intent."""
        queue_id = _insert_queue(connection, identifier, 1)
        connection.execute('INSERT INTO agent_transfer_deliveries '
                           '(id,generation,queue_id,claim,state,publication,files_directory,updated) '
                           'VALUES (?,1,?,0,?,?,?,?)',
                           (identifier, queue_id, 'queued', '{}', '', time.time()))

    def requeue(self, connection: Any, identifier: str, *, ceilings: list[str]) -> None:
        """Explicitly queue a new generation; any retained publication can only be inspected by its worker."""
        row = self.read(connection, identifier)
        if row['state'] != 'requires_review':
            raise AgentTaskError('destination publication ownership requires review')
        generation = row['generation'] + 1
        queue_id = _insert_queue(connection, identifier, generation)
        connection.execute("UPDATE agent_transfer_deliveries SET generation=?,queue_id=?,claim=0,state='queued',"
                           'ceilings=?,updated=? WHERE id=?',
                           (generation, queue_id, json.dumps(ceilings), time.time(), identifier))

    def pin_ceilings(self, connection: Any, identifier: str, ceilings: list[str]) -> None:
        """Retain current restrictive origin references before waking an already queued delivery."""
        row = self.read(connection, identifier)
        if row['state'] != 'queued':
            raise AgentTaskError('destination import is no longer queued')
        connection.execute('UPDATE agent_transfer_deliveries SET ceilings=? WHERE id=?',
                           (json.dumps(ceilings), identifier))

    def read(self, connection: Any, identifier: str) -> dict:
        """Read only a real delivery associated with an accepted local import."""
        row = connection.execute('SELECT * FROM agent_transfer_deliveries WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise AgentTaskError('destination import delivery is unavailable')
        return {**dict(row), 'publication': json.loads(row['publication']), 'ceilings': json.loads(row['ceilings'])}

    def recover(self, connection: Any) -> None:
        """Keep only exact never-claimed work queued after exclusive runtime ownership has been reacquired."""
        rows = connection.execute("SELECT * FROM agent_transfer_deliveries WHERE state IN "
                                  "('queued','receiving','verified')").fetchall()
        for row in rows:
            queue = connection.execute('SELECT status,claim,reference,data FROM work_items WHERE id=? AND queue=?',
                                       (row['queue_id'], QUEUE)).fetchone()
            if _undispatched(row, queue):
                continue
            connection.execute("UPDATE agent_transfer_deliveries SET state='requires_review',"
                               'generation=generation+1,updated=? WHERE id=?', (time.time(), row['id']))
            connection.execute("UPDATE work_items SET status='failed',claim=claim+1,error=?,updated=? WHERE id=? "
                               "AND queue=? AND status IN ('new','in_progress')",
                               ('runtime restarted; import review required', time.time(), row['queue_id'], QUEUE))

    def claim(self, item: Any) -> None:
        """Bind an actual queue claim before the first receiver effect; no abandoned attempt is replayed."""
        with self.store.connection(write=True) as connection:
            row = self.read(connection, item.reference)
            if (row['state'] != 'queued' or not _delivery_data(item.data, row['id'], row['generation'])
                    or row['queue_id'] != item.id or row['claim'] != 0):
                raise AgentTaskError('destination delivery is stale or requires review')
            queue = connection.execute('SELECT status,claim FROM work_items WHERE id=? AND queue=?',
                                       (item.id, QUEUE)).fetchone()
            if queue is None or queue['status'] != 'in_progress' or queue['claim'] != item.claim:
                raise AgentTaskError('destination queue claim is no longer owned')
            connection.execute("UPDATE agent_transfer_deliveries SET claim=?,state='receiving',updated=? WHERE id=?",
                               (item.claim, time.time(), item.reference))

    def check(self, connection: Any, identifier: str, generation: int) -> dict:
        """Refuse a retired generation or any delivery whose exact queue performer lost its claim."""
        row = self.read(connection, identifier)
        queue = connection.execute('SELECT status,claim,reference FROM work_items WHERE id=? AND queue=?',
                                   (row['queue_id'], QUEUE)).fetchone()
        if row['generation'] != generation or row['state'] not in {'receiving', 'verified'}:
            raise AgentTaskError('destination delivery generation is no longer active')
        if (queue is None or queue['status'] != 'in_progress' or queue['claim'] != row['claim']
                or queue['reference'] != identifier):
            raise AgentTaskError('destination delivery queue claim changed')
        return row

    def advance(self, connection: Any, identifier: str, generation: int, state: str, *,
                publication: dict | None = None, files_directory: str = '') -> None:
        """Record a verified phase only while the same generation and queue claim remain authoritative."""
        if state not in {'receiving', 'verified', 'published', 'requires_review', 'expired'}:
            raise AgentTaskError('invalid destination import transition')
        row = self.check(connection, identifier, generation)
        connection.execute('UPDATE agent_transfer_deliveries SET state=?,publication=?,files_directory=?,updated=? '
                           'WHERE id=?', (state, json.dumps(row['publication'] if publication is None else publication),
                                         files_directory, time.time(), identifier))

    def staging_retired(self, connection: Any, identifier: str, witness: dict) -> None:
        """Acknowledge only a previously journaled allocation's cleanup without granting a delivery generation."""
        row = self.read(connection, identifier)
        publication = row['publication']
        if publication.get('staging') != witness:
            return
        publication['staging'] = {**witness, 'cleaned': True}
        connection.execute('UPDATE agent_transfer_deliveries SET publication=? WHERE id=?',
                           (json.dumps(publication), identifier))

    def cancel(self, connection: Any, identifier: str) -> None:
        """Fence only this import's producer; confirmed published files remain user output."""
        row = self.read(connection, identifier)
        if row['state'] in FINAL:
            return
        state = 'requires_review' if row['publication'] else 'cancelled'
        connection.execute('UPDATE agent_transfer_deliveries SET state=?,generation=generation+1,updated=? '
                           'WHERE id=?', (state, time.time(), identifier))
        connection.execute("UPDATE work_items SET status='failed',claim=claim+1,error=?,updated=? WHERE id=? "
                           "AND queue=? AND status IN ('new','in_progress')",
                           ('import cancelled', time.time(), row['queue_id'], QUEUE))

    def expire(self, connection: Any, identifier: str) -> None:
        """Fence an expired local receipt without changing its original deadline or deleting user output."""
        row = self.read(connection, identifier)
        if row['state'] == 'expired':
            return
        connection.execute("UPDATE agent_transfer_deliveries SET state='expired',generation=generation+1,updated=? "
                           'WHERE id=?', (time.time(), identifier))
        connection.execute("UPDATE work_items SET status='failed',claim=claim+1,error=?,updated=? WHERE id=? "
                           "AND queue=? AND status IN ('new','in_progress')",
                           ('import receipt expired', time.time(), row['queue_id'], QUEUE))

    def prunable(self, connection: Any, cutoff: float) -> list[str]:
        """Select only expired, revoked, released imports whose own delivery and queue work are terminal."""
        _deadline(cutoff)
        rows = connection.execute("SELECT i.id FROM agent_transfer_imports i "
            "JOIN agent_transfer_deliveries d ON d.id=i.id WHERE i.kind='import' AND i.held=0 "
            "AND i.state='revoked' AND i.expires<=? AND d.state='expired' "
            'AND EXISTS (SELECT 1 FROM agent_transfer_revocations r WHERE r.id=i.id) '
            'AND NOT EXISTS (SELECT 1 FROM work_items w WHERE '
            "(w.queue=? AND w.reference=i.id AND w.status NOT IN ('success','failed')) "
            'OR (w.id=d.queue_id AND (w.queue!=? OR w.reference!=i.id))) ORDER BY i.id LIMIT 200',
            (min(cutoff, time.time()), QUEUE, QUEUE)).fetchall()
        return [row['id'] for row in rows]

    def prune(self, connection: Any, cutoff: float) -> int:
        """Delete exact terminal metadata atomically; consent tombstones and all user files remain owned."""
        if not connection.in_transaction:
            raise AgentTaskError('import metadata cleanup requires the owning writer transaction')
        identifiers = self.prunable(connection, cutoff)
        for identifier in identifiers:
            connection.execute("DELETE FROM work_items WHERE queue=? AND reference=? "
                               "AND status IN ('success','failed')", (QUEUE, identifier))
            connection.execute('DELETE FROM agent_transfer_deliveries WHERE id=?', (identifier,))
            connection.execute("DELETE FROM agent_transfer_imports WHERE id=? AND kind='import'", (identifier,))
        return len(identifiers)
