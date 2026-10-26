"""Actual destination deliveries retain the original issuer and fence revoked or cancelled effects."""
from pathlib import Path
from threading import Event
import time

import pytest

from headless.test_agent_transfer_import import import_hosts
from headless.test_agent_transfer_peer_security import post
from je_auto_control.utils.rbac.users import UserStore


def review(server, exported, token, root):
    status, reply = post(server, '/agent/transfer', {'operation': 'review_import', 'request': {
        'source_host': 'source', 'export_id': exported['export_id'], 'target': 'import-files',
        'directory': str(root / 'received'), 'idempotency_key': 'lifecycle-import'}}, token=token)
    assert status == 200, reply
    return {'review': reply['review'], 'note': 'Approve this import only', 'idempotency_key': 'lifecycle-import'}


def operation(server, token, name, request):
    return post(server, '/agent/transfer', {'operation': name, 'request': request}, token=token)


def wait_import(server, token, identifier):
    deadline = time.monotonic() + 20
    while True:
        status, reply = operation(server, token, 'get_import', {'import_id': identifier})
        assert status == 200, reply
        row = reply['import']
        if row['state'] in {'published', 'requires_review', 'cancelled', 'expired'}:
            return row
        assert time.monotonic() < deadline, row
        time.sleep(0.25)


@pytest.mark.parametrize('boundary', ['after-reserve', 'after-consume'])
def test_profile_disable_inside_acceptance_rolls_back_the_exact_import(tmp_path, monkeypatch, boundary):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, _actor):
        request = review(server, exported, token, root)
        records = host.runtime.transfers.source.records
        method = 'reserve' if boundary == 'after-reserve' else 'consume_review'
        original = getattr(records, method)
        def mutate(connection, *args):
            result = original(connection, *args)
            connection.execute("UPDATE agent_target_controls SET enabled=0 WHERE name='import-files'")
            return result
        monkeypatch.setattr(records, method, mutate)
        status, _reply = operation(server, token, 'create_import', request)
        assert status == 409
        with host.runtime.store.connection() as connection:
            assert connection.execute('SELECT count(*) FROM agent_transfer_imports').fetchone()[0] == 0
            pending = connection.execute(
                "SELECT count(*) FROM work_items WHERE queue='agent_transfer_import'").fetchone()
            assert pending[0] == 0
        assert not (root / 'received').exists()


def test_cancel_fences_the_producer_before_receiving_chunks(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import transfer_import_files
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, _actor):
        request = review(server, exported, token, root)
        entered, release = Event(), Event()
        original = transfer_import_files.receive_chunks
        # Block the receiving phase, retaining the real HTTP peer and real store when released.
        def receive(*args):
            entered.set()
            assert release.wait(10)
            return original(*args)
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', receive)
        try:
            status, reply = operation(server, token, 'create_import', request)
            assert status == 200, reply
            identifier = reply['import']['import_id']
            assert entered.wait(5)
            status, cancelled = operation(server, token, 'cancel_import', {'import_id': identifier})
            assert status == 200, cancelled
            assert cancelled['import']['state'] == 'cancelled'
            release.set()
            assert wait_import(server, token, identifier)['state'] == 'cancelled'
            with host.runtime.store.connection() as connection:
                row = connection.execute('SELECT generation FROM agent_transfer_deliveries WHERE id=?',
                                         (identifier,)).fetchone()
                assert row['generation'] == 2
            assert not (root / 'received').exists()
        finally:
            release.set()


def test_actual_recipient_revocation_before_receiving_never_publishes(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import transfer_import_files
    with import_hosts(tmp_path, monkeypatch) as (_host, server, exported, _body, token, root, actor):
        request = review(server, exported, token, root)
        original = transfer_import_files.receive_chunks
        def receive(*args):
            UserStore(actor.store_path).set_role('recipient', 'viewer')
            return original(*args)
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', receive)
        status, reply = operation(server, token, 'create_import', request)
        assert status == 200, reply
        # Inspection is read-only, but HTTP transfer management may reject a now-viewer caller.
        deadline = time.monotonic() + 10
        while True:
            with _host.runtime.store.connection() as connection:
                row = connection.execute('SELECT state FROM agent_transfer_deliveries WHERE id=?',
                                         (reply['import']['import_id'],)).fetchone()
            if row['state'] == 'requires_review':
                break
            assert time.monotonic() < deadline, row['state']
            time.sleep(0.05)
        assert not (root / 'received').exists()


def test_cancel_after_confirmed_publication_preserves_user_files(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as (_host, server, exported, body, token, root, _actor):
        status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
        assert status == 200, reply
        identifier = reply['import']['import_id']
        current = wait_import(server, token, identifier)
        assert current['state'] == 'published', current
        files = Path(current['files_directory'])
        status, cancelled = operation(server, token, 'cancel_import', {'import_id': identifier})
        assert status == 200, cancelled
        assert cancelled['import']['state'] == 'published'
        assert (files / 'report.txt').read_bytes() == body


def test_stopping_an_attached_observer_keeps_the_same_service_import_and_runtime_owner(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, transfer_import_files
    from je_auto_control.utils.agent_runtime.transfer_import import TransferImporter
    from je_auto_control.utils.rbac.users import UserStore
    from je_auto_control.utils.rest_api.rest_server import RestApiServer
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, actor):
        entered, release = Event(), Event()
        dispatched = []
        receive, deliver = transfer_import_files.receive_chunks, TransferImporter.deliver
        def paused(*args):
            entered.set()
            assert release.wait(10)
            return receive(*args)
        def observed(importer, identifier, *args):
            dispatched.append(identifier)
            return deliver(importer, identifier, *args)
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', paused)
        monkeypatch.setattr(TransferImporter, 'deliver', observed)
        attached = None
        try:
            status, created = operation(server, token, 'create_import', review(server, exported, token, root))
            assert status == 200, created
            identifier = created['import']['import_id']
            assert entered.wait(5)
            with host.runtime.store.connection() as connection:
                original = host.runtime.transfers.source.records.find(connection, identifier)
                before = host.runtime.transfers._life.importer._state.jobs.ledger.read(connection, identifier)
            server.stop()
            assert host.status()['running'] is True
            with pytest.raises(AgentTaskError, match='still owns'):
                AgentRuntime(host.runtime.store.path, targets={})
            attached = RestApiServer(port=0, token='owned-reattached-observer', user_store=UserStore(actor.store_path),
                agent_runtime=host.runtime, enable_audit=False, use_environment_users=False)
            attached.start()
            release.set()
            current = wait_import(attached, token, identifier)
            assert current['state'] == 'published', current
            assert dispatched == [identifier]
            assert (Path(current['files_directory']) / 'report.txt').read_bytes() == body
            with host.runtime.store.connection() as connection:
                after = host.runtime.transfers.source.records.find(connection, identifier)
                delivered = host.runtime.transfers._life.importer._state.jobs.ledger.read(connection, identifier)
            assert delivered['generation'] == before['generation']
            assert delivered['queue_id'] == before['queue_id']
            assert after['scope'] == original['scope'] and after['expires'] == original['expires']
            assert host.runtime.list() == []
        finally:
            release.set()
            if attached is not None:
                attached.stop()


@pytest.mark.parametrize('operation_name', ['create_import', 'run_import'])
def test_committed_import_reply_does_not_wait_for_the_new_background_writer(tmp_path, monkeypatch, operation_name):
    from concurrent.futures import ThreadPoolExecutor
    import sqlite3
    from je_auto_control.utils.agent_runtime.transfer_import_jobs import TransferImportJobs
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, _actor):
        request = review(server, exported, token, root)
        if operation_name == 'run_import':
            with monkeypatch.context() as scoped:
                scoped.setattr(TransferImportJobs, 'wake', lambda _jobs: None)
                status, queued = operation(server, token, 'create_import', request)
                assert status == 200, queued
            request = {'import_id': queued['import']['import_id']}
        entered, release = Event(), Event()
        writing = []
        original = TransferImportJobs.wake
        def hold_writer():
            with sqlite3.connect(host.runtime.store.path, timeout=1) as connection:
                connection.execute('BEGIN EXCLUSIVE')
                entered.set()
                assert release.wait(10)
        with ThreadPoolExecutor(max_workers=1) as workers:
            def wake(jobs):
                writing.append(workers.submit(hold_writer))
                assert entered.wait(5)
                original(jobs)
            monkeypatch.setattr(TransferImportJobs, 'wake', wake)
            try:
                status, reply = operation(server, token, operation_name, request)
                assert status == 200, reply
                assert reply['import']['state'] == 'queued'
            finally:
                release.set()
            for owned in writing:
                owned.result(timeout=5)
        identifier = reply['import']['import_id']
        current = wait_import(server, token, identifier)
        assert current['state'] == 'published', current
        assert (Path(current['files_directory']) / 'report.txt').read_bytes() == body


def test_cancel_cleanup_waits_for_the_exact_producer_and_preserves_other_accounts(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import transfer_import_files
    from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
    from hashlib import sha256
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, _actor):
        entered, release, retired = Event(), Event(), Event()
        original = transfer_import_files.receive_chunks
        def receive(*args):
            original(*args)
            entered.set()
            try:
                assert release.wait(10)
            finally:
                retired.set()
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', receive)
        try:
            status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
            assert status == 200, reply
            identifier = reply['import']['import_id']
            assert entered.wait(5)
            cache = PrivateTransferCache(host.runtime.store.path)
            foreign = 'f' * 32
            cache.store.put_chunk(foreign, sha256(b'unrelated').hexdigest(), b'unrelated')
            with host.runtime.store.connection() as connection:
                row = host.runtime.transfers.source.records.find(connection, identifier)
            assert cache.store.status(row['account'])['chunks'] > 0
            status, reply = operation(server, token, 'cancel_import', {'import_id': identifier})
            assert status == 200, reply
            host.runtime.transfers.maintain()
            assert cache.store.status(row['account'])['chunks'] > 0, 'a live producer still owns this account'
            release.set()
            assert retired.wait(5)
            deadline = time.monotonic() + 10
            while cache.store.status(row['account'])['chunks']:
                host.runtime.transfers.maintain()
                assert time.monotonic() < deadline
                time.sleep(0.05)
            assert cache.store.read_chunk(foreign, sha256(b'unrelated').hexdigest()) == b'unrelated'
            with host.runtime.store.connection() as connection:
                assert host.runtime.transfers.source.records.find(connection, identifier)['held'] is False
            assert not (root / 'received').exists()
        finally:
            release.set()


def test_replaced_queue_claim_fences_old_bytes_and_keeps_the_new_claim_unsettled(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import transfer_import_files
    from je_auto_control.utils.agent_runtime.transfer_import import TransferImporter
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, _actor):
        original = transfer_import_files.receive_chunks
        failed = Event()
        original_failure = TransferImporter.delivery_failed
        def failure(importer, *args):
            try:
                return original_failure(importer, *args)
            finally:
                failed.set()
        monkeypatch.setattr(TransferImporter, 'delivery_failed', failure)
        def replace_claim(record, *args):
            original(record, *args)
            with host.runtime.store.connection(write=True) as connection:
                row = connection.execute('SELECT queue_id FROM agent_transfer_deliveries WHERE id=?',
                                         (record['id'],)).fetchone()
                connection.execute('UPDATE work_items SET claim=claim+1 WHERE id=?', (row['queue_id'],))
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', replace_claim)
        status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
        assert status == 200, reply
        identifier = reply['import']['import_id']
        assert failed.wait(10)
        status, reply = operation(server, token, 'get_import', {'import_id': identifier})
        assert status == 200, reply
        current = reply['import']
        assert current['state'] == 'requires_review', current
        with host.runtime.store.connection() as connection:
            row = connection.execute('SELECT w.status,w.claim FROM work_items w JOIN agent_transfer_deliveries d '
                                     'ON d.queue_id=w.id WHERE d.id=?', (identifier,)).fetchone()
        assert row['status'] == 'in_progress'
        assert row['claim'] == 2
        assert not (root / 'received').exists()


def test_origin_added_at_approval_remains_binding_in_the_background_worker(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import origin_policy, transfer_import_files
    from je_auto_control.utils.agent_runtime.origin_policy import OriginWitness, origin_scope
    from je_auto_control.utils.rbac.authorization import authorization_scope
    monkeypatch.setattr(origin_policy, '_directory', lambda: tmp_path / 'origins')
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, actor):
        request = review(server, exported, token, root)
        witness = OriginWitness((root,))
        entered, release = Event(), Event()
        original = transfer_import_files.receive_chunks
        def receive(*args):
            entered.set()
            assert release.wait(10)
            return original(*args)
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', receive)
        try:
            with authorization_scope(actor), origin_scope(witness.identifier):
                created = host.runtime.transfers.control('create_import', request)
            assert entered.wait(5)
            witness.revoke()
            release.set()
            current = wait_import(server, token, created['import']['import_id'])
            assert current['state'] == 'requires_review', current
            assert not (root / 'received').exists()
        finally:
            release.set()


def test_destination_expiry_cleans_only_private_chunks_while_source_and_user_output_remain(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from je_auto_control.utils.agent_runtime import transfer_import
    from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
    from je_auto_control.utils.rbac.authorization import authorization_scope
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, actor):
        status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
        assert status == 200, reply
        identifier = reply['import']['import_id']
        current = wait_import(server, token, identifier)
        assert current['state'] == 'published', current
        files = Path(current['files_directory'])
        unrelated = root / 'unrelated.txt'
        unrelated.write_bytes(b'preserve this user output')
        with host.runtime.store.connection() as connection:
            record = host.runtime.transfers.source.records.find(connection, identifier)
        cache = PrivateTransferCache(host.runtime.store.path)
        assert cache.store.status(record['account'])['chunks'] > 0
        # Only the destination's wall clock advances. Source authority, bytes and clock stay real.
        monkeypatch.setattr(transfer_import, 'time', SimpleNamespace(
            time=lambda: record['expires'] + 1, monotonic=time.monotonic))
        deadline = time.monotonic() + 10
        while True:
            host.runtime.transfers.maintain()
            with host.runtime.store.connection() as connection:
                current_record = host.runtime.transfers.source.records.find(connection, identifier)
            if not current_record['held']:
                break
            assert time.monotonic() < deadline, 'expired destination still retains its private byte reservation'
            time.sleep(0.05)
        assert cache.store.status(record['account']) == {'bytes': 0, 'chunks': 0, 'blobs': 0}
        status, reply = operation(server, token, 'get_import', {'import_id': identifier})
        assert status == 200, reply
        assert reply['import']['state'] == 'expired'
        assert reply['import']['files_directory'] is None
        assert current_record['expires'] == record['expires']
        assert (files / 'report.txt').read_bytes() == body
        assert unrelated.read_bytes() == b'preserve this user output'
        with authorization_scope(actor):
            source = host.runtime.transfers.remote.call('source', host.runtime.batches.transfer_binding('source'),
                'export', {'export_id': exported['export_id']}, 5)
        assert source == exported['manifest'], 'destination expiry cannot revoke or refresh the source grant'


def test_expired_account_cleanup_failure_retains_capacity_until_a_confirmed_retry(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from je_auto_control.utils.agent_runtime import transfer_import
    from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, _actor):
        status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
        assert status == 200, reply
        identifier = reply['import']['import_id']
        current = wait_import(server, token, identifier)
        assert current['state'] == 'published', current
        controller = host.runtime.transfers
        jobs = controller._life.importer._state.jobs
        deadline = time.monotonic() + 10
        while not jobs.retired(identifier):
            assert time.monotonic() < deadline
            time.sleep(0.05)
        with host.runtime.store.connection() as connection:
            record = controller.source.records.find(connection, identifier)
        original = PrivateTransferCache.delete_account
        def fail_cleanup(_cache, _account):
            raise OSError('owned cleanup failure')
        # Serialize with actual service maintenance; both attempts still execute the production cleanup.
        with controller._mutex:
            monkeypatch.setattr(transfer_import, 'time', SimpleNamespace(
                time=lambda: record['expires'] + 1, monotonic=time.monotonic))
            monkeypatch.setattr(PrivateTransferCache, 'delete_account', fail_cleanup)
            with pytest.raises(OSError, match='owned cleanup failure'):
                controller.maintain()
            with host.runtime.store.connection() as connection:
                failed = controller.source.records.find(connection, identifier)
            assert failed['held'] is True
            assert failed['state'] == 'revoked'
            monkeypatch.setattr(PrivateTransferCache, 'delete_account', original)
            controller.maintain()
            with host.runtime.store.connection() as connection:
                cleaned = controller.source.records.find(connection, identifier)
            assert cleaned['held'] is False
        assert cleaned['expires'] == record['expires']
        assert (Path(current['files_directory']) / 'report.txt').read_bytes() == body


def test_cancel_after_actual_http_chunk_reply_rejects_the_late_cache_write(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
    from je_auto_control.utils.agent_runtime.transfer_transport import TransferPeer
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, _actor):
        entered, release, returned = Event(), Event(), Event()
        original = TransferPeer.call
        def delayed(peer, source_host, binding, name, request, timeout):
            reply = original(peer, source_host, binding, name, request, timeout)
            if name == 'chunk':
                entered.set()
                try:
                    assert release.wait(10)
                finally:
                    returned.set()
            return reply
        monkeypatch.setattr(TransferPeer, 'call', delayed)
        try:
            status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
            assert status == 200, reply
            identifier = reply['import']['import_id']
            assert entered.wait(5), 'the actual registered source HTTP chunk reply must be read first'
            with host.runtime.store.connection() as connection:
                record = host.runtime.transfers.source.records.find(connection, identifier)
            status, cancelled = operation(server, token, 'cancel_import', {'import_id': identifier})
            assert status == 200, cancelled
            release.set()
            assert returned.wait(5)
            assert wait_import(server, token, identifier)['state'] == 'cancelled'
            cache = PrivateTransferCache(host.runtime.store.path)
            assert cache.store.status(record['account'])['chunks'] == 0
            assert not (root / 'received').exists()
        finally:
            release.set()


def test_cancel_between_filesystem_publication_and_receipt_acceptance_requires_review(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import transfer_import_files
    with import_hosts(tmp_path, monkeypatch) as (_host, server, exported, body, token, root, _actor):
        entered, release = Event(), Event()
        publications = []
        original = transfer_import_files.publish_import
        def published(*args):
            result = original(*args)
            publications.append(result)
            entered.set()
            assert release.wait(10)
            return result
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.publish_import', published)
        try:
            status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
            assert status == 200, reply
            identifier = reply['import']['import_id']
            assert entered.wait(5)
            assert (publications[0].directory / 'report.txt').read_bytes() == body
            status, cancelled = operation(server, token, 'cancel_import', {'import_id': identifier})
            assert status == 200, cancelled
            assert cancelled['import']['state'] == 'requires_review', cancelled
            assert cancelled['import']['files_directory'] is None
            release.set()
            assert wait_import(server, token, identifier)['state'] == 'requires_review'
            assert (publications[0].directory / 'report.txt').read_bytes() == body
        finally:
            release.set()


def test_current_receipt_maintenance_does_not_reserve_an_idle_database_writer(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, _actor):
        status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
        assert status == 200, reply
        assert wait_import(server, token, reply['import']['import_id'])['state'] == 'published'
        controller = host.runtime.transfers
        original = host.runtime.store.connection
        writes = []
        def observed(*args, **kwargs):
            if kwargs.get('write'):
                writes.append(True)
            return original(*args, **kwargs)
        # Keep other service maintenance outside this exact observation without bypassing any storage operation.
        with controller._mutex:
            with monkeypatch.context() as scoped:
                scoped.setattr(host.runtime.store, 'connection', observed)
                controller.maintain()
        assert writes == [], 'a current published receipt has no cleanup or expiry mutation to reserve'
