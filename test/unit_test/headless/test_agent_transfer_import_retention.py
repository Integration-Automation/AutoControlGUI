"""Expired destination metadata retires only after owned producers and private bytes are gone."""
from contextlib import contextmanager
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from headless.test_agent_transfer_import import import_hosts
from headless.test_agent_transfer_import_lifecycle import operation, review, wait_import
from headless.test_agent_transfer_records import make_records, record, activate
from je_auto_control.utils.agent_runtime import (
    AgentRuntime, AgentTaskError, transfer_import, transfer_import_ledger, transfer_records,
)
from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
from je_auto_control.utils.agent_runtime.transfer_records import TransferRecords
from je_auto_control.utils.agent_runtime.transfer_import_ledger import QUEUE, TransferImportLedger
from je_auto_control.utils.work_queue.work_queue import WorkQueue


@contextmanager
def completed_import(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as values:
        host, server, exported, body, token, root, _actor = values
        request = review(server, exported, token, root)
        status, created = operation(server, token, 'create_import', request)
        assert status == 200, created
        identifier = created['import']['import_id']
        result = wait_import(server, token, identifier)
        assert result['state'] == 'published', result
        jobs = host.runtime.transfers._life.importer._state.jobs
        deadline = time.monotonic() + 10
        while not jobs.retired(identifier):
            assert time.monotonic() < deadline
            time.sleep(0.05)
        with host.runtime.store.connection() as connection:
            record = host.runtime.transfers.source.records.find(connection, identifier)
            intent = dict(connection.execute('SELECT * FROM agent_transfer_intents WHERE id=?',
                                             (identifier,)).fetchone())
        yield values, record, intent, result, request


@pytest.mark.parametrize('restart', [False, True])
def test_expired_import_metadata_and_delivery_are_pruned_without_recreating_consent(tmp_path, monkeypatch, restart):
    with completed_import(tmp_path, monkeypatch) as prepared:
        (host, server, _exported, body, token, root, _actor), record, intent, result, request = prepared
        unrelated = root / 'unrelated.txt'
        unrelated.write_bytes(b'preserve user output')
        runtime = host.runtime
        if restart:
            server.stop()
            host.close()
            runtime = AgentRuntime(runtime.store.path, targets={})
            assert runtime._transfers is None
        try:
            clock = SimpleNamespace(time=lambda: record['expires'] + 1)
            for module in (transfer_import, transfer_import_ledger, transfer_records):
                monkeypatch.setattr(module, 'time', clock)
            runtime.maintain()
            runtime.maintain()
            with runtime.store.connection() as connection:
                for table in ('agent_transfer_imports', 'agent_transfer_deliveries'):
                    assert connection.execute(f'SELECT 1 FROM {table} WHERE id=?', (record['id'],)).fetchone() is None
                assert connection.execute("SELECT 1 FROM work_items WHERE queue='agent_transfer_import' "
                                          'AND reference=?', (record['id'],)).fetchone() is None
                assert dict(connection.execute('SELECT * FROM agent_transfer_intents WHERE id=?',
                                                (record['id'],)).fetchone()) == intent
                assert connection.execute('SELECT 1 FROM agent_transfer_revocations WHERE id=?',
                                          (record['id'],)).fetchone() is not None
            assert PrivateTransferCache(runtime.store.path).store.status(record['account']) == {
                'bytes': 0, 'chunks': 0, 'blobs': 0}
            assert (Path(result['files_directory']) / 'report.txt').read_bytes() == body
            assert unrelated.read_bytes() == b'preserve user output'
            if not restart:
                status, denied = operation(server, token, 'create_import', request)
                assert status == 409, denied
            else:
                with runtime.store.connection(write=True) as connection, pytest.raises(AgentTaskError) as failure:
                    TransferRecords(runtime.store).reserve(connection, {name: value for name, value in record.items()
                        if name not in {'state', 'held', 'note_hash', 'key_hash'}} | {'key': 'lifecycle-import'})
                assert 'transfer' in str(failure.value)
        finally:
            if restart:
                runtime.close()


def retired_metadata(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    WorkQueue(records.store.path, QUEUE)
    ledger = TransferImportLedger(records.store)
    item = record(kind='import')
    activate(records, item)
    with records.store.connection(write=True) as connection:
        ledger.initialize(connection)
        ledger.enqueue(connection, item['id'])
        records.revoke(connection, item['id'])
        records.release(connection, item['id'])
        ledger.expire(connection, item['id'])
    return records, ledger, item


@pytest.mark.parametrize('guard', ['held', 'unexpired', 'delivery-active', 'queue-active', 'queue-rebound', 'foreign'])
def test_import_metadata_pruning_preserves_unsettled_or_unrelated_queue_ownership(tmp_path, monkeypatch, guard):
    records, ledger, item = retired_metadata(tmp_path, monkeypatch)
    monkeypatch.setattr(transfer_records.time, 'time', lambda: 2100.0)
    queue = WorkQueue(records.store.path, 'other' if guard == 'foreign' else QUEUE)
    extra = None
    if guard in {'queue-active', 'foreign'}:
        extra = queue.add({'import_id': item['id'], 'generation': 1}, reference=item['id'])
        assert queue.get_next().id == extra
    with records.store.connection(write=True) as connection:
        if guard == 'held':
            connection.execute('UPDATE agent_transfer_imports SET held=1 WHERE id=?', (item['id'],))
        elif guard == 'unexpired':
            monkeypatch.setattr(transfer_records.time, 'time', lambda: 1999.0)
        elif guard == 'delivery-active':
            connection.execute("UPDATE agent_transfer_deliveries SET state='requires_review' WHERE id=?", (item['id'],))
        elif guard == 'queue-rebound':
            connection.execute("UPDATE work_items SET reference='unrelated' WHERE queue=?", (QUEUE,))
        before = [tuple(row) for row in connection.execute('SELECT * FROM work_items ORDER BY id')]
        assert ledger.prune(connection, 3000.0) == int(guard == 'foreign')
        if guard != 'foreign':
            assert [tuple(row) for row in connection.execute('SELECT * FROM work_items ORDER BY id')] == before
            assert records.find(connection, item['id'])['held'] == (guard == 'held')
        else:
            foreign = connection.execute('SELECT * FROM work_items WHERE id=?', (extra,)).fetchone()
            assert tuple(foreign) == next(row for row in before if row[0] == extra)


def test_import_metadata_pruning_requires_a_writer_and_rolls_back_all_three_families(tmp_path, monkeypatch):
    records, ledger, item = retired_metadata(tmp_path, monkeypatch)
    monkeypatch.setattr(transfer_records.time, 'time', lambda: 2100.0)
    with records.store.connection() as connection, pytest.raises(AgentTaskError, match='writer'):
        ledger.prune(connection, 2100.0)
    with pytest.raises(RuntimeError, match='rollback after metadata deletion'):
        with records.store.connection(write=True) as connection:
            assert ledger.prune(connection, 2100.0) == 1
            raise RuntimeError('rollback after metadata deletion')
    with records.store.connection() as connection:
        assert records.find(connection, item['id'])['held'] is False
        assert ledger.read(connection, item['id'])['state'] == 'expired'
        assert connection.execute('SELECT count(*) FROM work_items WHERE queue=?', (QUEUE,)).fetchone()[0] == 1


def test_released_unexpired_metadata_cannot_hide_a_later_expired_private_account(tmp_path, monkeypatch):
    from hashlib import sha256
    records = make_records(tmp_path, monkeypatch)
    WorkQueue(records.store.path, QUEUE)
    ledger = TransferImportLedger(records.store)
    with records.store.connection(write=True) as connection:
        ledger.initialize(connection)
        for number in range(1, 202):
            item = record(number, kind='import', expires=3000.0)
            records.reserve(connection, item)
            records.consume_review(connection, item['review'], item['key'], 'approve metadata fixture')
            ledger.enqueue(connection, item['id'])
            records.revoke(connection, item['id'])
            records.release(connection, item['id'])
            ledger.expire(connection, item['id'])
        expired = record(202, kind='import')
        records.reserve(connection, expired)
        records.consume_review(connection, expired['review'], expired['key'], 'approve isolated expired fixture')
        ledger.enqueue(connection, expired['id'])
    cache = PrivateTransferCache(records.store.path)
    cache.store.put_chunk(expired['account'], sha256(b'private').hexdigest(), b'private')
    monkeypatch.setattr(transfer_records.time, 'time', lambda: 2100.0)
    runtime = AgentRuntime(records.store.path, targets={})
    try:
        assert runtime._transfers is None
        runtime.maintain()
        runtime.maintain()
        assert cache.store.status(expired['account']) == {'bytes': 0, 'chunks': 0, 'blobs': 0}
        with runtime.store.connection() as connection:
            assert connection.execute('SELECT count(*) FROM agent_transfer_imports').fetchone()[0] == 201
            assert connection.execute('SELECT 1 FROM agent_transfer_imports WHERE id=?',
                                      (expired['id'],)).fetchone() is None
            assert connection.execute('SELECT count(*) FROM agent_transfer_deliveries').fetchone()[0] == 201
    finally:
        runtime.close()
