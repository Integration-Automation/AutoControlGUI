"""Fixed-family handoff records and host-only access to explicitly granted evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


@dataclass(frozen=True)
class HandoffPolicy:
    """A host-derived effect ceiling and its actual private renewal provenance."""

    policy: Any
    renewed: bool


@dataclass(frozen=True)
class HandoffAccess:
    """A private validated projection; caller JSON cannot create task-read authority."""

    projection: dict
    rows: dict[str, dict]
    links: list[tuple[dict, dict, dict]]
    authority: HandoffPolicy
    witness: Callable
    grant: dict

    @property
    def policy(self) -> Any:
        """The current effect ceiling validated by the grant engine."""
        return self.authority.policy

    @property
    def renewed(self) -> bool:
        """Whether the actual leaf has privately reviewed renewal evidence."""
        return self.authority.renewed

    def read(self, identifier: str) -> dict:
        """Read only a real task already included in this explicitly validated grant."""
        if identifier not in self.rows:
            raise AgentTaskError('task is outside the explicit evidence handoff')
        return self.rows[identifier]

    def reply(self, identifier: str) -> dict:
        """Supply only the exact independently verified final completion projection."""
        if identifier != self.projection['task_id']:
            raise AgentTaskError('handoff does not select this completion task')
        return self.projection

    def __call__(self, connection: Any, source: dict, child: dict, link: dict) -> dict:
        """Recheck only an actual granted source/child pair through the injected host witness."""
        actual = next((item for item in self.links
                       if (item[0]['id'], item[1]['id']) == (source['id'], child['id'])), None)
        if actual is None or actual != (source, child, link):
            raise AgentTaskError('recovery pair is outside the explicit evidence handoff')
        return self.witness(connection, source, child, link, scope=self.policy)


class HandoffRecords:
    """Choose only fixed host-owned tables; all values remain bound SQL parameters."""

    def __init__(self, standalone: bool = False) -> None:
        self.standalone = standalone
        self._table = 'agent_task_handoffs' if standalone else 'agent_evidence_handoffs'
        self._revocations = 'agent_task_handoff_revocations' if standalone else 'agent_evidence_handoff_revocations'
        self.binding_fields = ('source_task',) if standalone else ('batch_id', 'node_id')

    def _sql(self, statement: str) -> str:
        return statement.replace('@records', self._table).replace('@revocations', self._revocations)

    def find(self, connection: Any, identifier: str) -> Any:
        """Look up one record in this actual storage family."""
        return connection.execute(self._sql('SELECT * FROM @records WHERE id=?'), (identifier,)).fetchone()

    def previous(self, connection: Any, review: str) -> Any:
        """Deduplicate only an active identical reviewed grant."""
        return connection.execute(self._sql("SELECT * FROM @records WHERE review=? AND state='active'"),
                                  (review,)).fetchone()

    def insert(self, connection: Any, row: dict) -> None:
        """Persist one family-shaped grant without inventing an unrelated DAG binding."""
        fields = ('id', *(() if self.standalone else ('batch_id', 'node_id')), 'source_task',
                  'task_id', 'review', 'details', 'note', 'state', 'created', 'expires')
        placeholders = ','.join('?' for _field in fields)
        statement = self._sql('INSERT INTO @records VALUES (@values)').replace('@values', placeholders)
        connection.execute(statement, tuple(row[field] for field in fields))

    def list(self, connection: Any, binding: dict) -> list:
        """List bounded history for this exact real source or DAG node."""
        filters = ' AND '.join(field + '=?' for field in self.binding_fields)
        statement = self._sql('SELECT * FROM @records WHERE @filter ORDER BY created DESC LIMIT 200')
        return connection.execute(statement.replace('@filter', filters),
                                  tuple(binding[field] for field in self.binding_fields)).fetchall()

    def revoke(self, connection: Any, identifier: str, actor: str, created: float) -> None:
        """Keep a durable revocation beside the revoked record in the same writer."""
        connection.execute(self._sql("UPDATE @records SET state='revoked' WHERE id=?"), (identifier,))
        connection.execute(self._sql('INSERT OR IGNORE INTO @revocations VALUES (?,?,?)'),
                           (identifier, actor, created))

    def current(self, connection: Any, identifier: str) -> tuple[Any, bool]:
        """Read the active state and irrevocable tombstone from one snapshot."""
        row = self.find(connection, identifier)
        revoked = connection.execute(self._sql('SELECT 1 FROM @revocations WHERE handoff_id=?'),
                                     (identifier,)).fetchone()
        return row, revoked is not None


def standalone_handoff(connection: Any, identifier: str) -> bool:
    """Resolve an actual persisted family; never accept a caller-authored table or authority mode."""
    found = [kind for kind in (False, True) if HandoffRecords(kind).find(connection, identifier) is not None]
    if len(found) > 1:
        raise AgentTaskError('handoff identity has ambiguous private bindings')
    return bool(found and found[0])
