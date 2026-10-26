"""Real destination service restarts preserve accepted consent and fence unsettled queue generations."""
from contextlib import contextmanager
from pathlib import Path
from threading import Event
import json
import time

import pytest

from headless.test_agent_transfer_import import import_hosts
from headless.test_agent_transfer_import_lifecycle import operation, review, wait_import
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.agent_runtime.transfer_import import TransferImporter
from je_auto_control.utils.agent_runtime.transfer_import_jobs import TransferImportJobs
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.rbac.users import UserStore
from je_auto_control.utils.rest_api.rest_server import RestApiServer


def queued_import(host, server, exported, token, root, monkeypatch):
    with monkeypatch.context() as scoped:
        scoped.setattr(TransferImportJobs, 'wake', lambda _jobs: None)
        status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
    assert status == 200, reply
    assert reply['import']['state'] == 'queued'
    return reply['import']['import_id']


@contextmanager
def restart_destination(host, server, actor):
    server.stop()
    host.close()
    restarted = AgentRuntimeService(host.directory, targets={})
    named = RestApiServer(port=0, token='owned-restarted-destination', user_store=UserStore(actor.store_path),
        agent_runtime=restarted.runtime, enable_audit=False, use_environment_users=False)
    try:
        restarted.start()
        named.start()
        yield restarted, named
    finally:
        named.stop()
        restarted.close()


def test_started_service_recovers_only_accepted_never_dispatched_import(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, actor):
        identifier = queued_import(host, server, exported, token, root, monkeypatch)
        with host.runtime.store.connection() as connection:
            before = host.runtime.transfers.source.records.find(connection, identifier)
        dispatched = Event()
        original = TransferImporter.deliver
        def deliver(importer, *args):
            dispatched.set()
            return original(importer, *args)
        monkeypatch.setattr(TransferImporter, 'deliver', deliver)
        with restart_destination(host, server, actor) as (restarted, named):
            assert dispatched.wait(5), 'an already approved unstarted import must be found by actual service startup'
            current = wait_import(named, token, identifier)
            assert current['state'] == 'published', current
            assert (Path(current['files_directory']) / 'report.txt').read_bytes() == body
            with restarted.runtime.store.connection() as connection:
                after = restarted.runtime.transfers.source.records.find(connection, identifier)
            assert after['expires'] == before['expires']
            assert after['scope'] == before['scope']
            assert restarted.runtime.list() == []


@pytest.mark.parametrize('revoked', [False, True])
def test_old_delivery_schema_upgrade_preserves_accepted_origin_and_fixed_expiry(tmp_path, monkeypatch, revoked):
    import sqlite3
    from je_auto_control.utils.agent_runtime import origin_policy
    from je_auto_control.utils.agent_runtime.origin_policy import OriginWitness, origin_scope
    from je_auto_control.utils.rbac.authorization import authorization_scope
    monkeypatch.setattr(origin_policy, '_directory', lambda: tmp_path / 'origins')
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, actor):
        request = review(server, exported, token, root)
        witness = OriginWitness((root,))
        with monkeypatch.context() as scoped:
            scoped.setattr(TransferImportJobs, 'wake', lambda _jobs: None)
            with authorization_scope(actor), origin_scope(witness.identifier):
                created = host.runtime.transfers.control('create_import', request)
        identifier = created['import']['import_id']
        with host.runtime.store.connection() as connection:
            original = host.runtime.transfers.source.records.find(connection, identifier)
            queued = host.runtime.transfers._life.importer._state.jobs.ledger.read(connection, identifier)
        assert witness.identifier in original['scope']['destination']['origins']
        assert queued['ceilings'] == []
        # Materialize the prior physical schema only after all owned service workers have stopped.
        server.stop()
        host.close()
        assert Path(host.runtime.store.path).resolve().is_relative_to(tmp_path.resolve())
        with sqlite3.connect(host.runtime.store.path) as connection:
            connection.execute('ALTER TABLE agent_transfer_deliveries DROP COLUMN ceilings')
            columns = {row[1] for row in connection.execute('PRAGMA table_info(agent_transfer_deliveries)')}
            assert 'ceilings' not in columns
        if revoked:
            witness.revoke()
        with restart_destination(host, server, actor) as (restarted, named):
            current = wait_import(named, token, identifier)
            assert current['state'] == ('requires_review' if revoked else 'published'), current
            with restarted.runtime.store.connection() as connection:
                after = restarted.runtime.transfers.source.records.find(connection, identifier)
                delivered = restarted.runtime.transfers._life.importer._state.jobs.ledger.read(connection, identifier)
            assert after['scope'] == original['scope']
            assert after['expires'] == original['expires']
            assert delivered['queue_id'] == queued['queue_id']
            assert isinstance(delivered['ceilings'], list)
            if revoked:
                assert current['files_directory'] is None
                assert not (root / 'received').exists()
            else:
                assert (Path(current['files_directory']) / 'report.txt').read_bytes() == body


def test_multiple_resume_origins_remain_cumulative_after_their_calling_scopes_exit(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import origin_policy, transfer_import_files
    from je_auto_control.utils.agent_runtime.origin_policy import OriginWitness, origin_scope
    from je_auto_control.utils.rbac.authorization import authorization_scope
    monkeypatch.setattr(origin_policy, '_directory', lambda: tmp_path / 'origins')
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, actor):
        original_receive = transfer_import_files.receive_chunks
        def interrupted(*args):
            original_receive(*args)
            raise AgentTaskError('owned interruption after verified private chunks')
        def settled():
            assert wait_import(server, token, identifier)['state'] == 'requires_review'
            deadline = time.monotonic() + 5
            while not jobs.retired(identifier):
                assert time.monotonic() < deadline
                time.sleep(0.01)
            with host.runtime.store.connection() as connection:
                return jobs.ledger.read(connection, identifier)
        first_origin, second_origin = OriginWitness((root,)), OriginWitness((root,))
        with monkeypatch.context() as scoped:
            scoped.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', interrupted)
            status, created = operation(server, token, 'create_import', review(server, exported, token, root))
            assert status == 200, created
            identifier = created['import']['import_id']
            jobs = host.runtime.transfers._life.importer._state.jobs
            initial = settled()
            with host.runtime.store.connection() as connection:
                original = host.runtime.transfers.source.records.find(connection, identifier)
            with authorization_scope(actor), origin_scope(first_origin.identifier):
                host.runtime.transfers.control('run_import', {'import_id': identifier})
            first = settled()
            assert first_origin.identifier in first['ceilings']
        blocked, release = Event(), Event()
        take = jobs.queue.get_next
        def blocked_take():
            blocked.set()
            assert release.wait(5)
            return take()
        with monkeypatch.context() as scoped:
            scoped.setattr(jobs.queue, 'get_next', blocked_take)
            try:
                assert blocked.wait(5)
                with authorization_scope(actor), origin_scope(second_origin.identifier):
                    reply = host.runtime.transfers.control('run_import', {'import_id': identifier})
                assert reply['import']['state'] == 'queued'
                with host.runtime.store.connection() as connection:
                    second = jobs.ledger.read(connection, identifier)
                assert {first_origin.identifier, second_origin.identifier} <= set(second['ceilings'])
                assert initial['generation'] < first['generation'] < second['generation']
                assert len({initial['queue_id'], first['queue_id'], second['queue_id']}) == 3
                first_origin.revoke()
            finally:
                release.set()
        jobs.wake()
        final = settled()
        assert {first_origin.identifier, second_origin.identifier} <= set(final['ceilings'])
        with host.runtime.store.connection() as connection:
            retained = host.runtime.transfers.source.records.find(connection, identifier)
        assert retained['scope'] == original['scope']
        assert retained['expires'] == original['expires']
        assert not (root / 'received').exists()


@pytest.mark.parametrize('boundary', ['queue-claimed', 'ledger-claimed'])
def test_restart_fences_unsettled_claim_without_silently_replaying_it(tmp_path, monkeypatch, boundary):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, actor):
        identifier = queued_import(host, server, exported, token, root, monkeypatch)
        jobs = host.runtime.transfers._life.importer._state.jobs
        item = jobs.queue.get_next()
        assert item.reference == identifier
        if boundary == 'ledger-claimed':
            jobs.ledger.claim(item)
        with restart_destination(host, server, actor) as (restarted, named):
            status, reply = operation(named, token, 'get_import', {'import_id': identifier})
            assert status == 200, reply
            assert reply['import']['state'] == 'requires_review', reply
            with restarted.runtime.store.connection() as connection:
                delivery = connection.execute('SELECT generation FROM agent_transfer_deliveries WHERE id=?',
                                              (identifier,)).fetchone()
                queue = connection.execute('SELECT status,claim FROM work_items WHERE id=?', (item.id,)).fetchone()
            assert delivery['generation'] > item.data['generation']
            assert queue['status'] == 'failed'
            assert queue['claim'] > item.claim
            assert not (root / 'received').exists()


def test_restart_rejects_a_boolean_queue_generation_instead_of_treating_it_as_one(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, actor):
        identifier = queued_import(host, server, exported, token, root, monkeypatch)
        with host.runtime.store.connection(write=True) as connection:
            connection.execute('UPDATE work_items SET data=? WHERE reference=? AND queue=?',
                (json.dumps({'import_id': identifier, 'generation': True}), identifier, 'agent_transfer_import'))
        with restart_destination(host, server, actor) as (_restarted, named):
            status, reply = operation(named, token, 'get_import', {'import_id': identifier})
            assert status == 200, reply
            assert reply['import']['state'] == 'requires_review', reply
            assert not (root / 'received').exists()


def test_explicit_restart_resumes_owned_chunks_with_a_new_queue_generation(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import transfer_import_files
    from je_auto_control.utils.agent_runtime.transfer_transport import TransferPeer
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, actor):
        original = transfer_import_files.receive_chunks
        def interrupted(*args):
            original(*args)
            raise AgentTaskError('owned interruption after actual verified cache download')
        with monkeypatch.context() as scoped:
            scoped.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', interrupted)
            status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
            assert status == 200, reply
            identifier = reply['import']['import_id']
            assert wait_import(server, token, identifier)['state'] == 'requires_review'
        with host.runtime.store.connection() as connection:
            before = host.runtime.transfers.source.records.find(connection, identifier)
            old_queue = connection.execute('SELECT queue_id,generation FROM agent_transfer_deliveries WHERE id=?',
                                           (identifier,)).fetchone()
        with restart_destination(host, server, actor) as (restarted, named):
            other = UserStore(actor.store_path).rotate_token('other')
            status, _reply = operation(named, other, 'run_import', {'import_id': identifier})
            assert status == 409
            calls = []
            peer_call = TransferPeer.call
            def observed(peer, source_host, binding, name, request, timeout):
                calls.append(name)
                return peer_call(peer, source_host, binding, name, request, timeout)
            monkeypatch.setattr(TransferPeer, 'call', observed)
            status, reply = operation(named, token, 'run_import', {'import_id': identifier})
            assert status == 200, reply
            current = wait_import(named, token, identifier)
            assert current['state'] == 'published', current
            assert (Path(current['files_directory']) / 'report.txt').read_bytes() == body
            assert 'export' in calls and 'chunk' not in calls, 'resume rechecks the real grant and owned cached bytes'
            with restarted.runtime.store.connection() as connection:
                after = restarted.runtime.transfers.source.records.find(connection, identifier)
                delivery = connection.execute('SELECT queue_id,generation FROM agent_transfer_deliveries WHERE id=?',
                                              (identifier,)).fetchone()
            assert delivery['queue_id'] != old_queue['queue_id']
            assert delivery['generation'] > old_queue['generation']
            assert after['scope'] == before['scope']
            assert after['expires'] == before['expires']


def test_explicit_resume_retains_its_additional_origin_in_the_new_delivery(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import origin_policy
    from je_auto_control.utils.agent_runtime.origin_policy import OriginWitness, origin_scope
    from je_auto_control.utils.rbac.authorization import authorization_scope
    monkeypatch.setattr(origin_policy, '_directory', lambda: tmp_path / 'origins')
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, actor):
        identifier = queued_import(host, server, exported, token, root, monkeypatch)
        jobs = host.runtime.transfers._life.importer._state.jobs
        jobs.ledger.claim(jobs.queue.get_next())
        with restart_destination(host, server, actor) as (restarted, named):
            witness = OriginWitness((root,))
            with monkeypatch.context() as scoped:
                scoped.setattr(TransferImportJobs, 'wake', lambda _jobs: None)
                with authorization_scope(actor), origin_scope(witness.identifier):
                    reply = restarted.runtime.transfers.control('run_import', {'import_id': identifier})
                assert reply['import']['state'] == 'queued'
            witness.revoke()
            restarted.runtime.transfers._life.importer._state.jobs.wake()
            current = wait_import(named, token, identifier)
            assert current['state'] == 'requires_review', current
            assert not (root / 'received').exists()


def interrupted_publication(host, server, exported, token, root, monkeypatch):
    from je_auto_control.utils.agent_runtime import transfer_import_files
    original = transfer_import_files.publish_import
    def interrupted(*args):
        original(*args)
        raise AgentTaskError('owned interruption after filesystem publication, before receipt acceptance')
    with monkeypatch.context() as scoped:
        scoped.setattr('je_auto_control.utils.agent_runtime.transfer_import.publish_import', interrupted)
        status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
        assert status == 200, reply
        identifier = reply['import']['import_id']
        assert wait_import(server, token, identifier)['state'] == 'requires_review'
    with host.runtime.store.connection() as connection:
        delivery = host.runtime.transfers._life.importer._state.jobs.ledger.read(connection, identifier)
    return identifier, delivery['publication']


def test_restart_reconciles_owned_complete_generation_without_receiving_or_publishing_again(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, actor):
        identifier, publication = interrupted_publication(host, server, exported, token, root, monkeypatch)
        output = Path(publication['files_directory']) / 'report.txt'
        assert output.read_bytes() == body
        before = output.stat()
        with restart_destination(host, server, actor) as (_restarted, named):
            def forbidden(*_args):
                pytest.fail('reconciliation may only inspect the owned generation, never download or republish')
            monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', forbidden)
            monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.publish_import', forbidden)
            status, reply = operation(named, token, 'run_import', {'import_id': identifier})
            assert status == 200, reply
            current = wait_import(named, token, identifier)
            assert current['state'] == 'published', current
            assert Path(current['files_directory']) == output.parent
            after = output.stat()
            assert (after.st_ino, after.st_size, after.st_mtime_ns) == (
                before.st_ino, before.st_size, before.st_mtime_ns)
            assert output.read_bytes() == body


@pytest.mark.parametrize('change', ['unchanged', 'changed-bytes', 'disabled-target', 'revoked-extra-origin'])
def test_second_restart_keeps_approved_never_claimed_readonly_inspection(tmp_path, monkeypatch, change):
    from je_auto_control.utils.agent_runtime import origin_policy
    from je_auto_control.utils.agent_runtime.origin_policy import OriginWitness, origin_scope
    from je_auto_control.utils.rbac.authorization import authorization_scope
    monkeypatch.setattr(origin_policy, '_directory', lambda: tmp_path / 'origins')
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, actor):
        identifier, publication = interrupted_publication(host, server, exported, token, root, monkeypatch)
        output = Path(publication['files_directory']) / 'report.txt'
        before = output.stat()
        with restart_destination(host, server, actor) as (first, first_server):
            def forbidden(*_args):
                pytest.fail('a persisted inspection must never receive or publish again')
            monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', forbidden)
            monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.publish_import', forbidden)
            def approve():
                if change == 'revoked-extra-origin':
                    witness = OriginWitness((root,))
                    with authorization_scope(actor), origin_scope(witness.identifier):
                        return first.runtime.transfers.control('run_import', {'import_id': identifier}), witness
                status, reply = operation(first_server, token, 'run_import', {'import_id': identifier})
                assert status == 200, reply
                return reply, None
            with monkeypatch.context() as scoped:
                scoped.setattr(TransferImportJobs, 'wake', lambda _jobs: None)
                reply, witness = approve()
                assert reply['import']['state'] == 'queued'
            with first.runtime.store.connection() as connection:
                ledger = first.runtime.transfers._life.importer._state.jobs.ledger
                queued = ledger.read(connection, identifier)
                original = first.runtime.transfers.source.records.find(connection, identifier)
            if change == 'changed-bytes':
                body = b'preserve user edits across passive inspection'
                output.write_bytes(body)
                before = output.stat()
            elif change == 'disabled-target':
                with authorization_scope(actor):
                    first.runtime.target_profiles.control('disable', {'name': 'import-files'})
            elif change == 'revoked-extra-origin':
                assert witness.identifier in queued['ceilings']
                witness.revoke()
            with restart_destination(first, first_server, actor) as (second, second_server):
                current = wait_import(second_server, token, identifier)
                assert current['state'] == ('published' if change == 'unchanged' else 'requires_review'), current
                with second.runtime.store.connection() as connection:
                    delivered = second.runtime.transfers._life.importer._state.jobs.ledger.read(connection, identifier)
                    retained = second.runtime.transfers.source.records.find(connection, identifier)
                assert delivered['generation'] >= queued['generation']
                assert delivered['queue_id'] == queued['queue_id']
                assert delivered['ceilings'] == queued['ceilings']
                assert retained['scope'] == original['scope']
                assert retained['expires'] == original['expires']
        after = output.stat()
        assert (after.st_ino, after.st_size, after.st_mtime_ns) == (
            before.st_ino, before.st_size, before.st_mtime_ns)
        assert output.read_bytes() == body


def test_restart_refuses_changed_publication_identity_and_keeps_user_output(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, actor):
        identifier, publication = interrupted_publication(host, server, exported, token, root, monkeypatch)
        output = Path(publication['files_directory']) / 'report.txt'
        publication['identity'] = [0, 0]
        with host.runtime.store.connection(write=True) as connection:
            connection.execute('UPDATE agent_transfer_deliveries SET publication=? WHERE id=?',
                               (json.dumps(publication), identifier))
        with restart_destination(host, server, actor) as (_restarted, named):
            status, _reply = operation(named, token, 'run_import', {'import_id': identifier})
            assert status == 409
            assert wait_import(named, token, identifier)['state'] == 'requires_review'
            assert output.read_bytes() == body


@pytest.mark.parametrize('change', ['changed-bytes', 'disabled-target', 'revoked-source'])
def test_reconciliation_rechecks_actual_bytes_profile_and_source_grant(tmp_path, monkeypatch, change):
    from je_auto_control.utils.rbac.authorization import authorization_scope
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, actor):
        identifier, publication = interrupted_publication(host, server, exported, token, root, monkeypatch)
        output = Path(publication['files_directory']) / 'report.txt'
        expected = body
        with restart_destination(host, server, actor) as (restarted, named):
            if change == 'changed-bytes':
                expected = b'user edits must never be overwritten by reconciliation'
                output.write_bytes(expected)
            elif change == 'disabled-target':
                with authorization_scope(actor):
                    restarted.runtime.target_profiles.control('disable', {'name': 'import-files'})
            else:
                with authorization_scope(actor):
                    controller = restarted.runtime.transfers
                    controller.remote.manage('source', restarted.runtime.batches.transfer_binding('source'),
                        'revoke_export', {'export_id': exported['export_id']}, 3)
            status, reply = operation(named, token, 'run_import', {'import_id': identifier})
            assert status == (200 if change == 'changed-bytes' else 409), reply
            current = wait_import(named, token, identifier)
            assert current['state'] == 'requires_review', current
            assert current['files_directory'] is None
            assert output.read_bytes() == expected
