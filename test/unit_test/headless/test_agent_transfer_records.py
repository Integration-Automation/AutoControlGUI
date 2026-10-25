"""Real SQLite transfer reservations keep consent, quotas and cleanup ownership durable."""
from concurrent.futures import ThreadPoolExecutor
import importlib
import importlib.util
from threading import Barrier

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.store import AgentTaskStore

MODULE = 'je_auto_control.utils.agent_runtime.transfer_records'


def make_records(tmp_path, monkeypatch):
    assert importlib.util.find_spec(MODULE) is not None, 'private transfer records are not implemented'
    module = importlib.import_module(MODULE)
    monkeypatch.setattr(module.time, 'time', lambda: 1000.0)
    store = AgentTaskStore(tmp_path / 'runtime.sqlite3')
    result = module.TransferRecords(store)
    with store.connection(write=True) as connection:
        result.initialize(connection)
    return result


def record(number=1, **changes):
    result = {'id': f'{number:032x}', 'kind': 'export', 'actor': 'a' * 64,
              'review': f'{number + 1000:032x}', 'key': f'key-{number}',
              'scope': {'snapshot': 'b' * 64}, 'created': 1000.0, 'expires': 2000.0,
              'review_expires': 1300.0, 'size': 0, 'chunks': 0, 'account': f'{number + 2000:032x}'}
    result.update(changes)
    return result


def reserve(records, item):
    with records.store.connection(write=True) as connection:
        return records.reserve(connection, item)


def activate(records, item, note='approved'):
    with records.store.connection(write=True) as connection:
        records.reserve(connection, item)
        return records.consume_review(connection, item['review'], item['key'], note)


def test_reservation_needs_explicit_consent_and_exact_retry_survives_restart(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    item = record()
    assert reserve(records, item)['id'] == item['id']
    with records.store.connection() as connection:
        with pytest.raises(AgentTaskError):
            records.active(connection, item['id'])
    first = activate(records, item)
    assert first['id'] == item['id']
    again = type(records)(AgentTaskStore(records.store.path))
    with again.store.connection(write=True) as connection:
        again.initialize(connection)
        assert again.reserve(connection, item) == first
        assert again.consume_review(connection, item['review'], item['key'], 'approved') == first
        result = again.active(connection, item['id'])
    result['scope']['snapshot'] = 'changed detached view'
    with records.store.connection() as connection:
        assert records.active(connection, item['id'])['scope'] == item['scope']


@pytest.mark.parametrize('field,value', [('note', 'changed'), ('key', 'different')])
def test_consumed_review_cannot_change_approval_note_or_key(tmp_path, monkeypatch, field, value):
    records = make_records(tmp_path, monkeypatch)
    item = record()
    activate(records, item)
    values = {'note': 'approved', 'key': item['key']}
    values[field] = value
    with records.store.connection(write=True) as connection:
        with pytest.raises(AgentTaskError):
            records.consume_review(connection, item['review'], values['key'], values['note'])


@pytest.mark.parametrize('change', [
    {'id': 'f' * 32}, {'actor': 'c' * 64}, {'scope': {'snapshot': 'c' * 64}},
    {'account': 'e' * 32}, {'expires': 2001.0}, {'review': 'e' * 32},
])
def test_existing_id_review_or_key_cannot_be_rebound(tmp_path, monkeypatch, change):
    records = make_records(tmp_path, monkeypatch)
    item = record()
    activate(records, item)
    with pytest.raises(AgentTaskError):
        reserve(records, {**item, **change})


def test_revocation_and_expiry_do_not_release_reservations_or_recreate_consent(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    item = record(size=3, chunks=1)
    activate(records, item)
    with records.store.connection(write=True) as connection:
        records.revoke(connection, item['id'])
        with pytest.raises(AgentTaskError):
            records.active(connection, item['id'])
    with pytest.raises(AgentTaskError):
        activate(records, item)
    monkeypatch.setattr(importlib.import_module(MODULE).time, 'time', lambda: 2100.0)
    assert records.prune(2100.0) == {'removed': 0, 'held': 1}
    with records.store.connection(write=True) as connection:
        records.release(connection, item['id'])
    assert records.prune(2100.0) == {'removed': 1, 'held': 0}
    with pytest.raises(AgentTaskError):
        reserve(records, item)


def test_active_or_unconfirmed_cleanup_cannot_release_owned_capacity(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    item = record()
    activate(records, item)
    with records.store.connection(write=True) as connection:
        with pytest.raises(AgentTaskError):
            records.release(connection, item['id'])
    monkeypatch.setattr(importlib.import_module(MODULE).time, 'time', lambda: 2100.0)
    assert records.prune(2100.0) == {'removed': 0, 'held': 1}


def test_future_prune_cutoff_cannot_remove_unexpired_cleaned_metadata(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    item = record()
    activate(records, item)
    with records.store.connection(write=True) as connection:
        records.revoke(connection, item['id'])
        records.release(connection, item['id'])
    assert records.prune(2100.0) == {'removed': 0, 'held': 0}


def test_one_review_racing_two_notes_consumes_only_one_exact_consent(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    item = record()
    reserve(records, item)
    barrier = Barrier(2)

    def consume(note):
        barrier.wait(timeout=10)
        try:
            with records.store.connection(write=True) as connection:
                records.consume_review(connection, item['review'], item['key'], note)
        except AgentTaskError:
            return 'refused'
        return 'consumed'

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(consume, ('note-a', 'note-b'))) == ['consumed', 'refused']


def test_global_revocation_tombstone_rejects_even_a_previously_absent_identity(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    with records.store.connection(write=True) as connection:
        records.revoke(connection, record()['id'])
    with pytest.raises(AgentTaskError):
        reserve(records, record())


def test_private_blob_account_is_unique_across_families_even_after_cleanup(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    item = record()
    activate(records, item)
    for kind in ('export', 'import'):
        with pytest.raises(AgentTaskError):
            reserve(records, record(2, kind=kind, account=item['account']))
    with records.store.connection(write=True) as connection:
        records.revoke(connection, item['id'])
        records.release(connection, item['id'])
    monkeypatch.setattr(importlib.import_module(MODULE).time, 'time', lambda: 2100.0)
    assert records.prune(2100.0) == {'removed': 1, 'held': 0}
    with pytest.raises(AgentTaskError):
        reserve(records, record(3, account=item['account'], created=2100.0, review_expires=2400.0, expires=3100.0))


def test_expiry_blocks_exact_retry_and_active_metadata_without_clearing_bytes(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    item = record()
    activate(records, item)
    monkeypatch.setattr(importlib.import_module(MODULE).time, 'time', lambda: 2000.0)
    with pytest.raises(AgentTaskError):
        activate(records, item)
    with records.store.connection() as connection:
        with pytest.raises(AgentTaskError):
            records.active(connection, item['id'])
    assert records.prune(2000.0) == {'removed': 0, 'held': 1}


def test_late_failure_rolls_back_review_key_and_reservation_together(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    item = record()
    with pytest.raises(RuntimeError, match='crash'):
        with records.store.connection(write=True) as connection:
            records.reserve(connection, item)
            records.consume_review(connection, item['review'], item['key'], 'approved')
            raise RuntimeError('crash after consent before commit')
    assert records.prune(2100.0) == {'removed': 0, 'held': 0}
    assert activate(records, item)['id'] == item['id']


@pytest.mark.parametrize('kind,count,changes', [
    ('export', 128, {}), ('import', 16, {}),
    ('export', 16, {'size': 64 * 1024 * 1024, 'chunks': 256}),
    ('export', 16, {'size': 500, 'chunks': 500}),
])
def test_global_capacity_remains_held_after_revoke(tmp_path, monkeypatch, kind, count, changes):
    records = make_records(tmp_path, monkeypatch)
    with records.store.connection(write=True) as connection:
        for index in range(1, count + 1):
            records.reserve(connection, record(index, kind=kind, **changes))
            records.revoke(connection, f'{index:032x}')
    extra = dict(changes)
    if extra.get('chunks') == 500:
        extra.update(size=193, chunks=193)
    with pytest.raises(AgentTaskError):
        reserve(records, record(999, kind=kind, **extra))


def test_two_writers_cannot_overbook_last_retained_grant_slot(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    with records.store.connection(write=True) as connection:
        for index in range(1, 128):
            records.reserve(connection, record(index))
    barrier = Barrier(2)

    def claim(number):
        barrier.wait(timeout=10)
        try:
            reserve(records, record(number))
        except AgentTaskError:
            return 'refused'
        return 'reserved'

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(claim, (1001, 1002)))
    assert sorted(outcomes) == ['refused', 'reserved']


def test_cleaned_but_retained_source_grants_still_count_against_metadata_limit(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    with records.store.connection(write=True) as connection:
        for index in range(1, 129):
            item = record(index)
            records.reserve(connection, item)
            records.revoke(connection, item['id'])
            records.release(connection, item['id'])
    with pytest.raises(AgentTaskError):
        reserve(records, record(999))


def test_route_review_uses_own_family_and_exact_private_peer_binding(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    item = record(kind='route', account=None, scope={'host': 'destination', 'fingerprint': 'c' * 64,
                  'peer_review': 'd' * 32, 'digest': 'e' * 64, 'operation': 'create_import'})
    activate(records, item)
    with records.store.connection(write=True) as connection:
        with pytest.raises(AgentTaskError):
            records.consume_review(connection, item['scope']['peer_review'], item['key'], 'approved')
        assert connection.execute('SELECT count(*) FROM agent_transfer_grants').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM agent_transfer_routed_reviews').fetchone()[0] == 1
    changed = {**item, 'scope': {**item['scope'], 'fingerprint': 'f' * 64}}
    with pytest.raises(AgentTaskError):
        reserve(records, changed)


def test_review_deadline_is_not_refreshed_but_exact_consumed_retry_is_allowed(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    first, second = record(), record(2)
    activate(records, first)
    reserve(records, second)
    monkeypatch.setattr(importlib.import_module(MODULE).time, 'time', lambda: 1301.0)
    assert activate(records, first)['id'] == first['id']
    with records.store.connection(write=True) as connection:
        with pytest.raises(AgentTaskError):
            records.consume_review(connection, second['review'], second['key'], 'approved')
    with pytest.raises(AgentTaskError):
        reserve(records, record(3))


@pytest.mark.parametrize('change', [
    {'size': True}, {'chunks': True}, {'created': float('nan')}, {'expires': float('inf')},
    {'review_expires': 1300.1}, {'expires': 999.0}, {'kind': 'invented_table'},
    {'id': '../other'}, {'actor': ''}, {'key': ''}, {'key': 'x' * 257},
    {'size': 64 * 1024 * 1024 + 1}, {'chunks': -1}, {'account': '../other'},
    {'extra': 'unknown'}, {'scope': {'bad': float('nan')}}, {'scope': {'bad': object()}},
])
def test_invalid_private_reservation_never_commits(tmp_path, monkeypatch, change):
    records = make_records(tmp_path, monkeypatch)
    with pytest.raises(AgentTaskError):
        reserve(records, record(**change))
    assert records.prune(2100.0) == {'removed': 0, 'held': 0}


@pytest.mark.parametrize('note', ['', 'x' * 4001, None, True])
def test_invalid_note_does_not_consume_review(tmp_path, monkeypatch, note):
    records = make_records(tmp_path, monkeypatch)
    item = record()
    reserve(records, item)
    with records.store.connection(write=True) as connection:
        with pytest.raises(AgentTaskError):
            records.consume_review(connection, item['review'], item['key'], note)
        assert records.consume_review(connection, item['review'], item['key'], 'approved')['id'] == item['id']


def test_initialize_inside_writer_does_not_implicitly_commit_unrelated_changes(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError):
        with records.store.connection(write=True) as connection:
            connection.execute('CREATE TABLE owned_marker(value TEXT)')
            connection.execute("INSERT INTO owned_marker VALUES ('must roll back')")
            records.initialize(connection)
            raise RuntimeError('rollback initialization too')
    with records.store.connection() as connection:
        assert not connection.execute("SELECT name FROM sqlite_master WHERE name='owned_marker'").fetchall()
