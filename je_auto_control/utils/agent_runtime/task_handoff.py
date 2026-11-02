"""Real non-DAG source identity for explicit completion evidence, without fabricated admission."""
from __future__ import annotations

from contextlib import nullcontext
import json
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.rbac.authorization import current_authorization


# pylint: disable-next=too-few-public-methods  # reason: one context provider is the host-only injection boundary
class TaskHandoffContext:
    """Derive bounded source ancestry through injected host ownership/snapshot validators."""

    def __init__(self, runtime: Any, snapshot: Callable, identity: Callable, digest: Callable,
                 owns: Callable) -> None:
        self.runtime, self.snapshot, self.identity, self.digest, self.owns = runtime, snapshot, identity, digest, owns

    def context(self, source_task: str, *, origin_policies: list[str] | None = None,
                connection: Any = None, identity_only: bool = False) -> dict:
        """Bind a real task and any actual accepted request without making a synthetic DAG node."""
        transaction = self.runtime.store.connection() if connection is None else nullcontext(connection)
        with transaction as reading:
            source = self.runtime.store.read_task(reading, source_task)
            if not self.owns(source['owner'], current_authorization()):
                raise AgentTaskError('handoff source does not exist or belongs to another caller')
            ancestry = self._ancestry(reading, source)
            binding = {'kind': 'task_completion', 'source_task': source_task, 'owner': source['owner'],
                       'ancestry': ancestry}
            retained = [self.runtime.store.read_task(reading, item['task_id']) for item in ancestry]
        policy = None if identity_only else self.runtime.batches.handoff_policy(source, origin_policies)
        return {'binding': binding, 'source': source, 'state': source['state'], 'policy': policy,
                'ancestor_links': len(ancestry) - 1, 'retained_rows': retained}

    def _ancestry(self, connection: Any, source: dict) -> list:
        result, seen, row = [], set(), source
        for _index in range(17):
            if row['id'] in seen:
                break
            seen.add(row['id'])
            self._non_dag(connection, row)
            result.append({'task_id': row['id'], 'snapshot': self.snapshot(connection, row)['snapshot'],
                           'requests': self._requests(connection, row)})
            found = connection.execute('SELECT * FROM agent_task_recoveries WHERE task_id=?',
                                       (row['id'],)).fetchone()
            if found is None:
                self._retired(seen)
                return result
            link = dict(found)
            parent = self.runtime.store.read_task(connection, link['source_task'])
            if self.snapshot(connection, parent)['snapshot'] != link['snapshot']:
                raise AgentTaskError('handoff source ancestry snapshot changed')
            self.identity(self.runtime, connection, parent, row, link)
            row = parent
        raise AgentTaskError('handoff source has no bounded real recovery ancestry')

    @staticmethod
    def _non_dag(connection: Any, row: dict) -> None:
        admitted = connection.execute('SELECT 1 FROM agent_dag_local_tasks WHERE task_id=?',
                                      (row['id'],)).fetchone()
        submitted = connection.execute('SELECT 1 FROM agent_task_submissions WHERE task_id=?',
                                       (row['id'],)).fetchone()
        if 'dag_batch' in row['spec']['options'] or admitted is not None or submitted is not None:
            raise AgentTaskError('DAG evidence requires its actual batch and node handoff')

    def _requests(self, connection: Any, row: dict) -> list:
        requests = [dict(item) for item in connection.execute(
            'SELECT * FROM agent_request_keys WHERE task_id=? ORDER BY owner_key,key_hash', (row['id'],))]
        owner = json.dumps([row['owner'].get('user_id'), row['owner'].get('store_path')])
        if any(item['owner_key'] != owner or item['spec_hash'] != self.digest(row['spec']) for item in requests):
            raise AgentTaskError('handoff original accepted request witness changed')
        return requests

    def _retired(self, identifiers: set[str]) -> None:
        # pylint: disable-next=protected-access  # reason: ancestry cannot attest live or unwinding owned input
        with self.runtime._mutex:
            # pylint: disable-next=protected-access  # reason: read only this runtime's private lifecycle witnesses
            if any(identifier in self.runtime._leases or identifier in self.runtime._executing
                   for identifier in identifiers):
                raise AgentTaskError('handoff source ancestry input has not retired')
