"""Fence a failed remote adoption and request bounded pause only for its genuinely accepted dependents."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import _hex
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

_ERRORS = (AutoControlException, OSError, RuntimeError, ValueError, TypeError, LookupError)


def _dependents(nodes: list, source: str) -> set[str]:
    selected = {source}
    for _index in range(len(nodes)):
        enlarged = selected | {node['id'] for node in nodes if selected.intersection(node['depends_on'])}
        if enlarged == selected:
            break
        selected = enlarged
    return selected - {source}


def _accepted(reply: dict) -> str:
    version = reply.get('spec_match_contract')
    if (not isinstance(version, int) or isinstance(version, bool) or version != 1 or
            reply.get('found') is not True or reply.get('spec_match') != 'matches'):
        raise AgentTaskError('dependent pause requires its actual matching accepted request')
    task = reply.get('task')
    if not isinstance(task, dict):
        raise AgentTaskError('dependent pause task identity is unavailable')
    _hex(task.get('task_id', ''), 32)
    return task['task_id']


@dataclass(frozen=True)
class _OwnedPause:
    """Carry the actual coordinator account and one finite cleanup deadline across dependent lookups."""

    runtime: Any
    batch: dict
    connect: Callable
    owner: DeferredAuthorization = field(default_factory=DeferredAuthorization.capture)
    deadline: float = field(default_factory=lambda: time.monotonic() + 5)

    def _call(self, node: dict, operation: str, body: dict) -> dict:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTaskError('dependent pause cleanup deadline expired')
        with self.owner.scope():
            if node['host'] == 'local':
                return (self.runtime.lookup(body['idempotency_key'], body['spec']) if operation == 'lookup'
                        else self.runtime.pause(body['task_id']).to_dict())
            call = self.connect(node['host'])
            return call(operation, body, remaining)

    def request(self, node: dict, receipt: dict) -> dict:
        """Pause only an independently matched accepted request while retaining unknown retirement."""
        result = {'outcome': 'requires_review', 'task_id': receipt.get('task_id')}
        try:
            identifier = _accepted(self._call(node, 'lookup', {
                'idempotency_key': node['task']['idempotency_key'], 'spec': node['task']['spec']}))
            if node['host'] == 'local':
                self._local_admission(node, identifier)
            result['task_id'] = identifier
            self._call(node, 'pause', {'task_id': identifier})
        except _ERRORS:
            # Missing acknowledgement cannot clear the claim or certify remote input retirement.
            return result
        return result

    def _local_admission(self, node: dict, identifier: str) -> None:
        with self.runtime.store.connection() as connection:
            row = connection.execute('SELECT batch_id,node_id FROM agent_dag_local_tasks WHERE task_id=?',
                                     (identifier,)).fetchone()
        if row is None or (row['batch_id'], row['node_id']) != (self.batch['id'], node['id']):
            raise AgentTaskError('local dependent pause requires its original private admission')


def pause_dependents(runtime: Any, batch: dict, source: str, nodes: list, connections: Callable) -> None:
    """Preserve possible effects and never pause unrelated work, replay a claim or invent a retirement ACK."""
    selected = _dependents(nodes, source)
    pending = {}
    with runtime.store.connection(write=True) as connection:
        fenced = connection.execute("UPDATE agent_dag_batches SET state='waiting_review',attempt='',updated=? "
            "WHERE id=? AND attempt=? AND state IN ('running','succeeded')",
            (time.time(), batch['id'], batch['attempt'])).rowcount
        if not fenced:
            return
        rows = connection.execute('SELECT node_id,phase,receipt FROM agent_dag_nodes WHERE batch_id=?',
                                  (batch['id'],)).fetchall()
        for row in rows:
            if row['node_id'] in selected and row['phase'] in {'claimed', 'unknown'}:
                receipt = {'outcome': 'requires_review', 'task_id': json.loads(row['receipt']).get('task_id')}
                pending[row['node_id']] = receipt
                connection.execute("UPDATE agent_dag_nodes SET phase='unknown',receipt=?,updated=? "
                    'WHERE batch_id=? AND node_id=?', (json.dumps(receipt), time.time(), batch['id'], row['node_id']))
    pause = _OwnedPause(runtime, batch, connections)
    for node in nodes:
        if node['id'] in pending:
            receipt = pause.request(node, pending[node['id']])
            with runtime.store.connection(write=True) as connection:
                connection.execute("UPDATE agent_dag_nodes SET receipt=?,updated=? WHERE batch_id=? AND node_id=? "
                    "AND phase='unknown' AND EXISTS (SELECT 1 FROM agent_dag_batches b WHERE b.id=? "
                    "AND b.state='waiting_review' AND b.attempt='')",
                    (json.dumps(receipt), time.time(), batch['id'], node['id'], batch['id']))
