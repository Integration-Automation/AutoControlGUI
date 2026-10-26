"""Durable provisional consent blocks dispatch until fresh remote proof passes outside the local writer."""
from __future__ import annotations

import time
import json
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

_ERRORS = (AutoControlException, OSError, RuntimeError, ValueError, TypeError, LookupError)


def remote_reports(batch: dict, reports: list[dict]) -> list[dict]:
    """Select actual remote handoff decisions from the immutable coordinator graph."""
    hosts = {node['id']: node['host'] for node in batch['definition']['nodes']}
    return [report for report in reports if 'handoff_id' in report['decision']
            and hosts[report['decision']['node_id']] != 'local']


class DagTransferChecks:
    """A persisted pending phase supplies no authority to dispatch or accept downstream completion."""

    def __init__(self, store: Any, batch: dict, verify: Callable[[], None], *, baseline: dict | None = None) -> None:
        self.store, self.batch, self.verify = store, batch, verify
        self.pinned: tuple | None = None
        self.owner = DeferredAuthorization.capture()
        with store.connection() as connection:
            self.local = self._snapshot(connection)
        expected = tuple(batch[name] for name in ('id', 'state', 'attempt', 'graph_hash',
                                                  'owner', 'definition', 'hosts', 'max_parallel'))
        if self.local[0] != expected:
            raise AgentTaskError('coordinator changed before provisional remote consent')
        if baseline is not None:
            self._baseline(baseline)

    def _baseline(self, baseline: dict) -> None:
        nodes = tuple(tuple(row[name] for name in ('node_id', 'phase', 'receipt', 'updated'))
                      for row in sorted(baseline['nodes'], key=lambda item: item['node_id']))
        bindings = tuple(sorted(baseline['batch']['bindings'].items()))
        inputs = baseline['batch']['input_definition']
        if self.local[1:] != (nodes, bindings, inputs):
            raise AgentTaskError('coordinator node claims or bindings changed during remote review')

    def _snapshot(self, connection: Any) -> tuple:
        row = connection.execute('SELECT id,state,attempt,graph_hash,owner,definition,hosts,max_parallel '
                                 'FROM agent_dag_batches WHERE id=?', (self.batch['id'],)).fetchone()
        nodes = connection.execute('SELECT node_id,phase,receipt,updated FROM agent_dag_nodes '
                                   'WHERE batch_id=? ORDER BY node_id', (self.batch['id'],)).fetchall()
        bindings = connection.execute('SELECT node_id,task FROM agent_dag_bindings '
                                      'WHERE batch_id=? ORDER BY node_id', (self.batch['id'],)).fetchall()
        inputs = connection.execute('SELECT definition FROM agent_dag_inputs WHERE batch_id=?',
                                    (self.batch['id'],)).fetchone()
        identity = None if row is None else (tuple(row[:4]) + tuple(json.loads(row[name]) for name in
                                            ('owner', 'definition', 'hosts')) + (row['max_parallel'],))
        return (identity, tuple(tuple(item) for item in nodes),
                tuple((item['node_id'], json.loads(item['task'])) for item in bindings),
                None if inputs is None else json.loads(inputs[0]))

    def _approval(self, connection: Any, identifier: str) -> tuple:
        row = connection.execute('SELECT id,batch_id,source_snapshot,plan_hash,details,created '
            'FROM agent_dag_approvals WHERE id=? AND batch_id=?', (identifier, self.batch['id'])).fetchone()
        if row is None:
            raise AgentTaskError('provisional remote consent is unavailable')
        return tuple(row)

    def pin(self, connection: Any, identifier: str) -> None:
        """Retain the exact accepted immutable payload while the original pending writer still owns it."""
        self.pinned = self._approval(connection, identifier)

    def guard(self, connection: Any, identifier: str, phase: str) -> None:
        """Recheck exact local state under its writer before a pending phase can become authoritative."""
        row = connection.execute('SELECT state FROM agent_dag_approvals WHERE id=? AND batch_id=?',
                                 (identifier, self.batch['id'])).fetchone()
        if (row is None or row['state'] != phase or self._snapshot(connection) != self.local or
                self._approval(connection, identifier) != self.pinned):
            raise AgentTaskError('provisional remote consent or coordinator state changed')

    def finish(self, identifier: str, phase: str, commit: Callable) -> None:
        """Resolve outside the writer, then atomically accept only the same still-pending local intent."""
        try:
            with self.owner.scope():
                self.verify()
                with self.store.connection(write=True) as connection, self.owner.scope():
                    self.guard(connection, identifier, phase)
                    commit(connection)
        except _ERRORS:
            self.cancel(identifier)
            raise

    def cancel(self, identifier: str) -> None:
        """Keep failed or interrupted provisional work non-dispatchable without resetting delivery claims."""
        with self.store.connection(write=True) as connection:
            changed = connection.execute("UPDATE agent_dag_approvals SET state='cancelled' WHERE id=? "
                "AND batch_id=? AND state IN ('provisional','starting')", (identifier, self.batch['id'])).rowcount
            if changed:
                connection.execute("UPDATE agent_dag_batches SET state='waiting_review',attempt='',updated=? "
                                   "WHERE id=? AND state='approved'", (time.time(), self.batch['id']))
