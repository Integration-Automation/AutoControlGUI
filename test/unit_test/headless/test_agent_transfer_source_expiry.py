"""Actual source expiry retires only its private bytes and keeps ownership until cleanup is confirmed."""
from hashlib import sha256
from types import SimpleNamespace

import pytest

from headless.test_agent_transfer_source import completed_source, create_for, review_for
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, transfer_records, transfer_source
from je_auto_control.utils.agent_runtime.file_target import FileTarget


@pytest.mark.parametrize('boundary', ['expiry', 'cleanup-failure', 'restart', 'revoked-issuer'])
def test_source_expiry_cleans_owned_cache_and_preserves_user_output_and_foreign_account(
        tmp_path, monkeypatch, boundary):
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
    with completed_source(tmp_path, named=boundary == 'revoked-issuer') as (runtime, task, output, body, users):
        actor = AuthorizationContext('owner', 'operator', store_path=str(users.path)) if users else None
        with authorization_scope(actor):
            exported = create_for(runtime, review_for(runtime, task))
        source = runtime.transfers.source
        with runtime.store.connection() as connection:
            original = source.records.find(connection, exported['export_id'])
        foreign, foreign_body = 'f' * 32, b'preserve unrelated private account'
        digest = sha256(foreign_body).hexdigest()
        source._cache.store.put_chunk(foreign, digest, foreign_body)
        source_clock = SimpleNamespace(time=lambda: original['expires'] + 1)
        monkeypatch.setattr(transfer_source, 'time', source_clock)
        monkeypatch.setattr(transfer_records, 'time', source_clock)
        if boundary == 'revoked-issuer':
            users.remove_user('owner')
        if boundary == 'restart':
            runtime.close()
            runtime = AgentRuntime(runtime.store.path, targets={'local-files': FileTarget()})
        try:
            source = runtime.transfers.source
            if boundary == 'cleanup-failure':
                with monkeypatch.context() as scoped, pytest.raises(OSError, match='owned expiry cleanup failure'):
                    def failed(account):
                        assert account == original['account']
                        raise OSError('owned expiry cleanup failure')
                    scoped.setattr(source._cache, 'delete_account', failed)
                    runtime.transfers.maintain()
                with runtime.store.connection() as connection:
                    retained = source.records.find(connection, exported['export_id'])
                assert retained['state'] == 'revoked' and retained['held'] is True
                assert source._cache.store.status(original['account'])['chunks'] > 0
            runtime.maintain()
            with runtime.store.connection() as connection:
                retained = source.records.find(connection, exported['export_id'])
                assert connection.execute('SELECT 1 FROM agent_transfer_intents WHERE id=?',
                                          (exported['export_id'],)).fetchone() is not None
                assert connection.execute('SELECT 1 FROM agent_transfer_revocations WHERE id=?',
                                          (exported['export_id'],)).fetchone() is not None
            assert retained['state'] == 'revoked' and retained['held'] is False
            assert retained['expires'] == original['expires']
            assert retained['scope'] == original['scope']
            assert source._cache.store.status(original['account']) == {'bytes': 0, 'chunks': 0, 'blobs': 0}
            assert source._cache.store.read_chunk(foreign, digest) == foreign_body
            assert output.read_bytes() == body
            with pytest.raises(AgentTaskError):
                runtime.transfers.peer('export', {'export_id': exported['export_id']})
        finally:
            if boundary == 'restart':
                runtime.close()


def test_source_maintenance_holds_runtime_ownership_until_exact_cleanup_finishes(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        exported = create_for(runtime, review_for(runtime, task))
        controller = runtime.transfers
        source = controller.source
        with runtime.store.connection() as connection:
            record = source.records.find(connection, exported['export_id'])
        monkeypatch.setattr(transfer_source, 'time', SimpleNamespace(time=lambda: record['expires'] + 1))
        entered, release = Event(), Event()
        original = source._cache.delete_account
        def blocked(account):
            assert account == record['account']
            entered.set()
            assert release.wait(10)
            return original(account)
        monkeypatch.setattr(source._cache, 'delete_account', blocked)
        with ThreadPoolExecutor(max_workers=1) as workers:
            cleaning = workers.submit(controller.maintain)
            try:
                assert entered.wait(5)
                with pytest.raises(AgentTaskError, match='active transfer'):
                    runtime.close()
                with pytest.raises(AgentTaskError, match='still owns'):
                    AgentRuntime(runtime.store.path, targets={'local-files': FileTarget()})
            finally:
                release.set()
            cleaning.result(timeout=5)
        with runtime.store.connection() as connection:
            assert source.records.find(connection, record['id'])['held'] is False


@pytest.mark.parametrize('state', ['absent', 'active', 'cleaned-live'])
def test_source_maintenance_without_candidates_never_acquires_a_writer(tmp_path, monkeypatch, state):
    from contextlib import contextmanager
    with completed_source(tmp_path) as (runtime, task, output, body, _users):
        controller = runtime.transfers
        if state != 'absent':
            exported = create_for(runtime, review_for(runtime, task))
            if state == 'cleaned-live':
                controller.control('revoke_export', {'export_id': exported['export_id']})
        original = runtime.store.connection
        @contextmanager
        def readonly(*args, **kwargs):
            assert not kwargs.get('write'), 'idle transfer maintenance must not acquire an unnecessary writer'
            with original(*args, **kwargs) as connection:
                yield connection
        with monkeypatch.context() as scoped:
            scoped.setattr(runtime.store, 'connection', readonly)
            controller.maintain()
        assert output.read_bytes() == body


def test_source_expiry_does_not_retire_another_live_export_of_the_same_bytes(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, first_task, output, body, _users):
        first = create_for(runtime, review_for(runtime, first_task))
        second_task = runtime.submit({'goal': 'independently verify the same current file', 'target': 'local-files',
            'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(tmp_path)],
            'success_criteria': [{'kind': 'file_sha256', 'path': str(output), 'value': sha256(body).hexdigest()}]})
        assert runtime.finish(second_task.task_id).state == 'succeeded'
        second_review = runtime.transfers.control('review_export', {'source_task': second_task.task_id,
            'selection': [{'criterion': 0, 'names': []}], 'recipient_policy': 'caller',
            'idempotency_key': 'independent-live-export'})
        second = runtime.transfers.control('create_export', {'review': second_review['review'],
            'note': 'Approve independently verified live bytes',
            'idempotency_key': 'independent-live-export'})['export']
        source = runtime.transfers.source
        with runtime.store.connection() as connection:
            old = source.records.find(connection, first['export_id'])
            live = source.records.find(connection, second['export_id'])
        assert old['expires'] < live['expires']
        clock = SimpleNamespace(time=lambda: old['expires'] + (live['expires'] - old['expires']) / 2)
        monkeypatch.setattr(transfer_source, 'time', clock)
        monkeypatch.setattr(transfer_records, 'time', clock)
        runtime.transfers.maintain()
        assert source._cache.store.status(old['account'])['chunks'] == 0
        assert source._cache.store.status(live['account'])['chunks'] > 0
        assert runtime.transfers.peer('export', {'export_id': second['export_id']}) == second['manifest']
        with runtime.store.connection() as connection:
            retained = source.records.find(connection, second['export_id'])
        assert retained['held'] is True and retained['state'] == 'active'
        assert retained['expires'] == live['expires']
        assert output.read_bytes() == body


@pytest.mark.parametrize('restart', [False, True])
def test_later_maintenance_prunes_cleaned_expired_source_metadata_without_recreating_consent(
        tmp_path, monkeypatch, restart):
    with completed_source(tmp_path) as (runtime, task, output, body, _users):
        review = review_for(runtime, task)
        exported = create_for(runtime, review)
        with runtime.store.connection() as connection:
            record = runtime.transfers.source.records.find(connection, exported['export_id'])
            intent = dict(connection.execute('SELECT * FROM agent_transfer_intents WHERE id=?',
                                             (record['id'],)).fetchone())
        clock = SimpleNamespace(time=lambda: record['expires'] + 1)
        monkeypatch.setattr(transfer_source, 'time', clock)
        monkeypatch.setattr(transfer_records, 'time', clock)
        runtime.maintain()
        if restart:
            runtime.close()
            runtime = AgentRuntime(runtime.store.path, targets={'local-files': FileTarget()})
        try:
            runtime.maintain()
            with runtime.store.connection() as connection:
                assert connection.execute('SELECT 1 FROM agent_transfer_grants WHERE id=?',
                                          (record['id'],)).fetchone() is None
                retained = dict(connection.execute('SELECT * FROM agent_transfer_intents WHERE id=?',
                                                  (record['id'],)).fetchone())
                assert retained == intent
                assert connection.execute('SELECT 1 FROM agent_transfer_revocations WHERE id=?',
                                          (record['id'],)).fetchone() is not None
            with pytest.raises(AgentTaskError):
                create_for(runtime, review)
            assert output.read_bytes() == body
        finally:
            if restart:
                runtime.close()


def test_cold_runtime_maintenance_does_not_construct_an_unused_transfer_controller(tmp_path):
    from je_auto_control.utils.agent_runtime.transfer_cache import private_cache_path
    runtime = AgentRuntime(tmp_path / 'empty-runtime.sqlite3', targets={})
    try:
        assert runtime._transfers is None
        runtime.maintain()
        assert runtime._transfers is None
        assert not private_cache_path(runtime.store.path).exists()
    finally:
        runtime.close()
