"""Bind artifact authority to real bounded recovery ancestry and original accepted DAG admission."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.rbac.authorization import AuthorizationContext
from je_auto_control.utils.rbac.deferred import DeferredAuthorization


@dataclass(frozen=True)
class SourceLineage:
    """Reuse host recovery witnesses without issuing completion grants or fabricating child admission."""

    runtime: Any
    digest: Callable
    submitted: Callable
    manager: Callable
    retired: Callable
    ownership: Callable

    def context(self, connection: Any, leaf: dict, issuer: dict, origins: list[str] | None) -> dict:
        """Check original requests, current owners and every real historical recovery segment."""
        rows, links = self._chain(connection, leaf, issuer)
        root = rows[0]
        context, accepted = self._root(connection, root, origins)
        requests = [self._requests(connection, row) for row in rows]
        if accepted is not None and not requests[0]:
            raise AgentTaskError('tagged source original accepted request witness is unavailable')
        policies, segments = self._segments(connection, context, links, issuer, origins)
        proof = {'binding': context['binding'], 'requests': requests,
                 'snapshots': [self.runtime.recovery.handoff_snapshot(connection, row) for row in rows],
                 'recovery_ownership': [self.ownership(connection, row['id']) for row in rows],
                 'authorization': context.get('completion_authorization'), 'segments': segments}
        return {'digest': self.digest(proof), 'policies': tuple(policies),
                'owners': self._principals(rows, context, proof['recovery_ownership']),
                'submission_digest': accepted if accepted is not None else self.submitted(root['spec'])}

    @staticmethod
    def _principals(rows: list, context: dict, ownership: list) -> tuple[dict, ...]:
        owners = tuple(row['owner'] for row in rows)
        admission = context['binding'].get('admission')
        if admission is not None:
            owners += (json.loads(admission['actor']),)
        for value in ownership:
            if value is not None:
                owners += (value['actor'], value['owner'])
        return owners

    def _segments(self, connection: Any, context: dict, links: list, issuer: dict,
                  origins: list[str] | None) -> tuple[tuple, list]:
        if not links:
            return (), []
        context['issuer'] = issuer
        context.update(self.runtime.recovery.handoff_scope(connection, context, links, origins, None, issuing=True))
        scope = (context['policy'] if context.get('evidence_scope') or
                 context.get('completion_authorization') is not None else None)
        segments = [self.runtime.recovery.handoff_witness(connection, parent, child, link, scope=scope)
                    for parent, child, link in links]
        return (context['policy'],), segments

    def _chain(self, connection: Any, leaf: dict, issuer: dict) -> tuple[list, list]:
        rows, seen, row = [leaf], set(), leaf
        links: list[tuple[dict, dict, dict]] = []
        for _index in range(17):
            if row['id'] in seen or not self.retired(row['id']):
                raise AgentTaskError('source recovery ancestry is cyclic or input has not retired')
            seen.add(row['id'])
            self.manager(issuer, row['owner'])
            with DeferredAuthorization(AuthorizationContext(**row['owner']) if row['owner'] else None).scope():
                pass
            if connection.execute('SELECT 1 FROM agent_control WHERE owner=?', (row['id'],)).fetchone():
                raise AgentTaskError('source recovery ancestry still owns input control')
            found = connection.execute('SELECT * FROM agent_task_recoveries WHERE task_id=?', (row['id'],)).fetchone()
            if found is None:
                return list(reversed(rows)), list(reversed(links))
            link = dict(found)
            parent = self.runtime.store.read_task(connection, link['source_task'])
            links.append((parent, row, link))
            rows.append(parent)
            row = parent
        raise AgentTaskError('source exceeds sixteen real recovery links')

    def _root(self, connection: Any, root: dict, origins: list[str] | None) -> tuple[dict, str | None]:
        accepted = connection.execute('SELECT spec_digest FROM agent_task_submissions WHERE task_id=?',
                                      (root['id'],)).fetchone()
        admitted = connection.execute('SELECT * FROM agent_dag_local_tasks WHERE task_id=?',
                                      (root['id'],)).fetchone()
        tag = self._tag(root, accepted, admitted)
        batch = None if tag is None else connection.execute('SELECT id FROM agent_dag_batches WHERE id=?',
                                                            (tag['batch_id'],)).fetchone()
        if admitted is not None or batch is not None:
            binding = dict(admitted) if admitted is not None else tag
            context = self._local_context(connection, root, binding, origins)
        else:
            context = {'binding': {'kind': 'task_completion', 'source_task': root['id'], 'owner': root['owner']},
                       'source': root, 'state': root['state'], 'policy': None}
        return context, accepted[0] if accepted is not None else None

    @staticmethod
    def _tag(root: dict, accepted: Any, admitted: Any) -> dict | None:
        tag = root['spec']['options'].get('dag_batch')
        if (accepted is not None or admitted is not None) and tag is None:
            raise AgentTaskError('source original DAG tag is missing')
        if tag is not None and accepted is None:
            raise AgentTaskError('tagged source original submission witness is unavailable')
        return tag

    def _local_context(self, connection: Any, root: dict, binding: dict | None, origins: list[str] | None) -> dict:
        if binding is None:
            raise AgentTaskError('source original local DAG binding is unavailable')
        context = self.runtime.batches.handoff_context(binding['batch_id'], binding['node_id'],
            origin_policies=origins, connection=connection, identity_only=True)
        if context['source']['id'] != root['id']:
            raise AgentTaskError('source differs from its original local DAG admission')
        self.manager(json.loads(context['binding']['admission']['actor']), root['owner'])
        return context

    def _requests(self, connection: Any, row: dict) -> list:
        requests = [dict(item) for item in connection.execute(
            'SELECT * FROM agent_request_keys WHERE task_id=? ORDER BY owner_key,key_hash', (row['id'],))]
        owner = json.dumps([row['owner'].get('user_id'), row['owner'].get('store_path')])
        if any(item['owner_key'] != owner or item['spec_hash'] != self.digest(row['spec']) for item in requests):
            raise AgentTaskError('source original accepted request witness changed')
        return requests

    def accepted_requests(self, connection: Any, row: dict) -> list:
        """Expose only actual validated private request witnesses to another host-owned proof builder."""
        return self._requests(connection, row)

    def evidence_context(self, connection: Any, source: dict, issuer: dict, origins: list[str] | None) -> dict:
        """Preserve actual local DAG admission; remote accepted nodes keep their real task-only context."""
        lineage = self.context(connection, source, issuer, origins)
        rows, _links = self._chain(connection, source, issuer)
        root = rows[0]
        context, _accepted = self._root(connection, root, origins)
        tagged = root['spec']['options'].get('dag_batch') is not None
        if tagged and root['id'] != source['id']:
            raise AgentTaskError('portable evidence must name the original accepted DAG source')
        if 'admission' not in context['binding']:
            context = {'binding': {'kind': 'task_completion', 'source_task': source['id'], 'owner': source['owner']},
                       'source': source, 'state': source['state'], 'policy': None,
                       'ancestor_links': len(rows) - 1, 'retained_rows': rows}
        context['binding'] = {**context['binding'], 'transfer_lineage_digest': lineage['digest']}
        return context
