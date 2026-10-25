"""Private transfer reservations bind consent and retain capacity until owned cleanup is confirmed."""
from __future__ import annotations

from hashlib import sha256
import json
import time
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import (
    MAX_MANIFEST_BYTES, MAX_TRANSFER_BYTES, _canonical, _deadline, _hex,
)

_FAMILIES = {'export': 'agent_transfer_grants', 'evidence': 'agent_transfer_grants',
             'import': 'agent_transfer_imports', 'route': 'agent_transfer_routed_reviews'}
_TABLES = tuple(dict.fromkeys(_FAMILIES.values()))
_FIELDS = {'id', 'kind', 'actor', 'review', 'key', 'scope', 'created', 'expires',
           'review_expires', 'size', 'chunks', 'account'}
_SCHEMA = (
    'CREATE TABLE IF NOT EXISTS @records (id TEXT PRIMARY KEY,kind TEXT NOT NULL,actor TEXT NOT NULL,'
    'review TEXT NOT NULL UNIQUE,key_hash TEXT NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,'
    'note_hash TEXT NOT NULL DEFAULT \'\',expires REAL NOT NULL,review_expires REAL NOT NULL,'
    'size INTEGER NOT NULL,chunks INTEGER NOT NULL,held INTEGER NOT NULL)',
    'CREATE INDEX IF NOT EXISTS @records_expiry ON @records(expires,held)',
)
_QUERIES = {
    'find': 'SELECT * FROM @records WHERE id=?',
    'totals': 'SELECT COALESCE(SUM(size),0),COALESCE(SUM(chunks),0) FROM @records WHERE held=1',
    'reserve': 'INSERT INTO @records '
               '(id,kind,actor,review,key_hash,payload,state,expires,review_expires,size,chunks,held) '
               'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
    'activate': "UPDATE @records SET state='active',note_hash=? WHERE id=?",
    'revoke': "UPDATE @records SET state='revoked' WHERE id=?",
    'release': 'UPDATE @records SET held=0 WHERE id=?',
    'held': 'SELECT count(*) FROM @records WHERE held=1 AND expires<=?',
    'prune': "DELETE FROM @records WHERE held=0 AND state!='active' AND expires<=?",
    'entries': 'SELECT * FROM @records WHERE kind=? ORDER BY id LIMIT 200',
}


def _sql(table: str, operation: str) -> str:
    if table not in _TABLES or operation not in _QUERIES:
        raise AgentTaskError('unsupported private transfer query')
    return _QUERIES[operation].replace('@records', table)


def _writer(connection: Any) -> None:
    if not connection.in_transaction:
        raise AgentTaskError('transfer mutation requires the owning writer transaction')


def _text(value: Any, limit: int, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise AgentTaskError('invalid transfer ' + label)
    try:
        return sha256(value.encode('utf-8')).hexdigest()
    except UnicodeError as error:
        raise AgentTaskError('invalid transfer ' + label) from error


def _payload(record: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(record, dict) or set(record) != _FIELDS:
        raise AgentTaskError('private transfer record has invalid or unknown fields')
    _hex(record['id'], 32)
    _hex(record['review'], 32)
    _hex(record['actor'], 64)
    kind = record['kind']
    if not isinstance(kind, str) or kind not in _FAMILIES:
        raise AgentTaskError('unsupported private transfer family')
    _capacity_fields(record)
    _record_times(record)
    if not isinstance(record['scope'], dict):
        raise AgentTaskError('transfer scope must be a host-derived object')
    key_hash = _text(record['key'], 256, 'idempotency key')
    values = {name: value for name, value in record.items() if name != 'key'}
    values['key_hash'] = key_hash
    try:
        encoded = _canonical(values)
    except (TypeError, ValueError, RecursionError, UnicodeError) as error:
        raise AgentTaskError('transfer scope must contain finite JSON data') from error
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise AgentTaskError('private transfer record exceeds one mebibyte')
    return encoded.decode('utf-8'), key_hash


def _capacity_fields(record: dict[str, Any]) -> None:
    for name, maximum in (('size', MAX_TRANSFER_BYTES), ('chunks', 8192)):
        value = record[name]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
            raise AgentTaskError('invalid transfer reservation ' + name)
    if record['kind'] in {'evidence', 'route'}:
        if record['size'] or record['chunks'] or record['account'] is not None:
            raise AgentTaskError('evidence and routed reviews cannot reserve byte accounts')
    else:
        _hex(record['account'], 32)


def _record_times(record: dict[str, Any]) -> None:
    for name in ('created', 'expires', 'review_expires'):
        _deadline(record[name])
    if not record['created'] < record['expires'] <= record['created'] + 30 * 86400:
        raise AgentTaskError('transfer retention must be fixed and bounded to thirty days')
    if not record['created'] < record['review_expires'] <= record['created'] + 300:
        raise AgentTaskError('transfer review must have its original five-minute deadline')


def _view(row: Any) -> dict[str, Any]:
    values = json.loads(row['payload'])
    values.update(state=row['state'], held=bool(row['held']), note_hash=row['note_hash'])
    return values


def _find(connection: Any, identifier: str) -> tuple[str, Any]:
    _hex(identifier, 32)
    found = []
    for table in _TABLES:
        row = connection.execute(_sql(table, 'find'), (identifier,)).fetchone()
        if row is not None:
            found.append((table, row))
    if len(found) != 1:
        raise AgentTaskError('transfer identity is missing or ambiguous')
    return found[0]


def _revoked(connection: Any, identifier: str) -> bool:
    return connection.execute('SELECT 1 FROM agent_transfer_revocations WHERE id=?',
                              (identifier,)).fetchone() is not None


def _quota(connection: Any, record: dict[str, Any]) -> None:
    grants = connection.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0]
    imports = connection.execute('SELECT count(*) FROM agent_transfer_imports WHERE held=1').fetchone()[0]
    if record['kind'] in {'export', 'evidence'} and grants >= 128:
        raise AgentTaskError('retained transfer grant quota exceeded')
    if record['kind'] == 'import' and imports >= 16:
        raise AgentTaskError('active or uncleared transfer import quota exceeded')
    size = chunks = 0
    for table in _TABLES:
        row = connection.execute(_sql(table, 'totals')).fetchone()
        size += row[0]
        chunks += row[1]
    if size + record['size'] > 1024**3 or chunks + record['chunks'] > 8192:
        raise AgentTaskError('aggregate transfer byte or chunk reservation quota exceeded')


class TransferRecords:
    """Trusted host-only storage; callers separately prove current actor, producer fencing and cleanup."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def initialize(self, connection: Any) -> None:
        """Create only fixed private tables without implicitly committing the caller's writer."""
        _writer(connection)
        for table in _TABLES:
            for statement in _SCHEMA:
                connection.execute(statement.replace('@records', table))
        connection.execute('CREATE TABLE IF NOT EXISTS agent_transfer_intents ('
                           'kind TEXT NOT NULL,actor TEXT NOT NULL,key_hash TEXT NOT NULL,'
                           'id TEXT NOT NULL UNIQUE,review TEXT NOT NULL UNIQUE,account TEXT UNIQUE,'
                           'digest TEXT NOT NULL,'
                           'PRIMARY KEY(kind,actor,key_hash))')
        connection.execute('CREATE TABLE IF NOT EXISTS agent_transfer_revocations (id TEXT PRIMARY KEY)')

    def reserve(self, connection: Any, record: dict[str, Any]) -> dict[str, Any]:
        """Reserve one exact host-derived intent and capacity under the existing SQLite writer."""
        _writer(connection)
        payload, key_hash = _payload(record)
        digest = sha256(payload.encode('utf-8')).hexdigest()
        previous = connection.execute(
            'SELECT * FROM agent_transfer_intents WHERE id=? OR review=? OR account=? '
            'OR (kind=? AND actor=? AND key_hash=?)',
            (record['id'], record['review'], record['account'], record['kind'], record['actor'], key_hash)).fetchall()
        if previous:
            return self._retry(connection, previous, digest)
        if _revoked(connection, record['id']):
            raise AgentTaskError('revoked transfer identity cannot be recreated')
        now = time.time()
        if record['created'] > now or min(record['expires'], record['review_expires']) <= now:
            raise AgentTaskError('transfer review is expired or not yet valid')
        _quota(connection, record)
        table = _FAMILIES[record['kind']]
        connection.execute('INSERT INTO agent_transfer_intents VALUES (?,?,?,?,?,?,?)',
                           (record['kind'], record['actor'], key_hash, record['id'], record['review'],
                            record['account'], digest))
        connection.execute(_sql(table, 'reserve'),
                           (record['id'], record['kind'], record['actor'], record['review'], key_hash, payload,
                            'reserved', record['expires'], record['review_expires'], record['size'], record['chunks'],
                            int(record['kind'] != 'route')))
        return _view(_find(connection, record['id'])[1])

    def _retry(self, connection: Any, previous: list[Any], digest: str) -> dict[str, Any]:
        if len(previous) != 1 or previous[0]['digest'] != digest:
            raise AgentTaskError('transfer key, review or identity already binds a different intent')
        row = _find(connection, previous[0]['id'])[1]
        if _revoked(connection, row['id']) or row['state'] not in {'reserved', 'active'}:
            raise AgentTaskError('transfer consent is no longer active')
        if row['expires'] <= time.time() or (row['state'] == 'reserved' and row['review_expires'] <= time.time()):
            raise AgentTaskError('transfer consent has expired')
        return _view(row)

    def consume_review(self, connection: Any, review: str, key: str, note: str) -> dict[str, Any]:
        """Activate one reserved intent, accepting only an identical already-consumed retry."""
        _writer(connection)
        _hex(review, 32)
        key_hash, note_hash = _text(key, 256, 'idempotency key'), _text(note, 4000, 'approval note')
        intent = connection.execute('SELECT * FROM agent_transfer_intents WHERE review=?', (review,)).fetchone()
        if intent is None or intent['key_hash'] != key_hash:
            raise AgentTaskError('transfer review does not bind this key')
        table, row = _find(connection, intent['id'])
        if _revoked(connection, row['id']) or row['expires'] <= time.time():
            raise AgentTaskError('transfer consent has expired or was revoked')
        if row['state'] == 'active' and row['note_hash'] == note_hash:
            return _view(row)
        if row['state'] != 'reserved' or row['review_expires'] <= time.time():
            raise AgentTaskError('transfer review is consumed or expired')
        connection.execute(_sql(table, 'activate'), (note_hash, row['id']))
        return _view(_find(connection, row['id'])[1])

    def active(self, connection: Any, identifier: str) -> dict[str, Any]:
        """Read detached current metadata; this primitive grants no actor or task-input authority."""
        row = _find(connection, identifier)[1]
        if _revoked(connection, identifier) or row['state'] != 'active' or row['expires'] <= time.time():
            raise AgentTaskError('transfer record is not active')
        return _view(row)

    def find(self, connection: Any, identifier: str) -> dict[str, Any]:
        """Inspect private metadata without treating an expired or revoked record as authority."""
        return _view(_find(connection, identifier)[1])

    def review(self, connection: Any, review: str) -> dict[str, Any] | None:
        """Resolve only an actually persisted local intent; peer tokens cannot select a different family."""
        _hex(review, 32)
        row = connection.execute('SELECT id FROM agent_transfer_intents WHERE review=?', (review,)).fetchone()
        return self.find(connection, row[0]) if row else None

    def entries(self, connection: Any, kind: str) -> list[dict[str, Any]]:
        """Return a bounded private family view for host-authorized management filtering."""
        if kind not in _FAMILIES:
            raise AgentTaskError('unsupported private transfer family')
        return [_view(row) for row in connection.execute(_sql(_FAMILIES[kind], 'entries'), (kind,))]

    def revoke(self, connection: Any, identifier: str) -> None:
        """Retire authority irreversibly while holding capacity for any surviving owned bytes."""
        _writer(connection)
        _hex(identifier, 32)
        connection.execute('INSERT OR IGNORE INTO agent_transfer_revocations VALUES (?)', (identifier,))
        for table in _TABLES:
            connection.execute(_sql(table, 'revoke'), (identifier,))

    def release(self, connection: Any, identifier: str) -> None:
        """Release a revoked reservation only after the host has fenced producers and confirmed own cleanup."""
        _writer(connection)
        table, row = _find(connection, identifier)
        if row['state'] != 'revoked' or not _revoked(connection, identifier):
            raise AgentTaskError('active transfer capacity cannot be released')
        connection.execute(_sql(table, 'release'), (identifier,))

    def prune(self, cutoff: float) -> dict[str, int]:
        """Remove only already-cleaned expired metadata, retaining intent and revocation tombstones."""
        _deadline(cutoff)
        cutoff = min(cutoff, time.time())
        removed = held = 0
        with self.store.connection(write=True) as connection:
            for table in _TABLES:
                held += connection.execute(_sql(table, 'held'), (cutoff,)).fetchone()[0]
                cursor = connection.execute(_sql(table, 'prune'), (cutoff,))
                removed += cursor.rowcount
        return {'removed': removed, 'held': held}
