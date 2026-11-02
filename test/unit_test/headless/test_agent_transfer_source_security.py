"""Source grants keep real role checks, owned producer retirement and exact byte permissions."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Event

import pytest

from headless.test_agent_transfer_source import completed_source, create_for, review_for
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.file_target import FileTarget
from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


def test_unconfirmed_completion_marker_cannot_create_a_source_review(tmp_path):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        with runtime.store.connection(write=True) as connection:
            connection.execute('UPDATE agent_completion SET contract=0 WHERE task_id=?', (task,))
        with pytest.raises(AgentTaskError):
            review_for(runtime, task)


@pytest.mark.parametrize('boundary', ['review', 'create', 'export', 'chunk'])
def test_tagged_source_cannot_replace_a_missing_real_submission_witness_with_a_computed_digest(tmp_path, boundary):
    with completed_source(tmp_path) as (runtime, _initial, output, body, _users):
        task = runtime.submit({'goal': 'verify an actual accepted tagged request', 'target': 'local-files',
            'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(tmp_path)],
            'success_criteria': [{'kind': 'file_sha256', 'path': str(output), 'value': sha256(body).hexdigest()}],
            'options': {'dag_batch': {'batch_id': 'a' * 32, 'graph_hash': 'b' * 64, 'node_id': 'file-node'}}},
            idempotency_key='actual-accepted-tagged-file-request')
        assert runtime.finish(task.task_id).state == 'succeeded'
        assert runtime.get(task.task_id).metadata['submission_contract'] == 1
        review = review_for(runtime, task.task_id) if boundary != 'review' else None
        exported = create_for(runtime, review) if boundary in {'export', 'chunk'} else None
        with runtime.store.connection(write=True) as connection:
            connection.execute('DELETE FROM agent_task_submissions WHERE task_id=?', (task.task_id,))
        with pytest.raises(AgentTaskError):
            if boundary == 'review':
                review_for(runtime, task.task_id)
            elif boundary == 'create':
                create_for(runtime, review)
            else:
                request = {'export_id': exported['export_id']}
                if boundary == 'chunk':
                    request['sha256'] = exported['manifest']['files'][0]['chunks'][0]
                runtime.transfers.peer(boundary, request)


@pytest.mark.parametrize('boundary', ['reserve', 'consume_review'])
@pytest.mark.parametrize('lost', ['owner', 'reviewer'])
def test_actual_principal_loss_after_source_sql_never_leaves_readable_authority(tmp_path, monkeypatch, boundary, lost):
    with completed_source(tmp_path, named=True) as (runtime, task, output, body, users):
        issuer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
        with authorization_scope(issuer):
            review = review_for(runtime, task, policy='source_owner')
            records = runtime.transfers.source.records
            original = getattr(records, boundary)
            def revoked(*args, **kwargs):
                result = original(*args, **kwargs)
                users.remove_user(lost)
                return result
            monkeypatch.setattr(records, boundary, revoked)
            with pytest.raises(AgentTaskError):
                create_for(runtime, review)
        assert output.read_bytes() == body
        with runtime.store.connection() as connection:
            rows = records.entries(connection, 'export')
        assert all(row['state'] != 'active' for row in rows)
        assert all(row['held'] is False for row in rows)


def test_off_manifest_hash_and_corrupted_actual_chunk_are_refused(tmp_path):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        created = create_for(runtime, review_for(runtime, task))
        source = runtime.transfers.source
        with pytest.raises(AgentTaskError):
            runtime.transfers.peer('chunk', {'export_id': created['export_id'], 'sha256': sha256(b'other').hexdigest()})
        with runtime.store.connection() as connection:
            record = source.records.find(connection, created['export_id'])
        digest = created['manifest']['files'][0]['chunks'][0]
        with source._cache.store._database.connection() as connection:
            connection.execute('UPDATE sync_asset_chunks SET body=? WHERE user_id=? AND digest=?',
                               (b'tampered', record['account'], digest))
        with pytest.raises(AgentTaskError):
            runtime.transfers.peer('chunk', {'export_id': created['export_id'], 'sha256': digest})


def test_runtime_close_refuses_active_source_work_and_keeps_the_real_owner_lock(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        review = review_for(runtime, task)
        source = runtime.transfers.source
        entered, release = Event(), Event()
        original = source._scan
        def blocked(*args, **kwargs):
            entered.set()
            assert release.wait(10), 'owned test worker did not receive its release'
            return original(*args, **kwargs)
        monkeypatch.setattr(source, '_scan', blocked)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(create_for, runtime, review)
            try:
                assert entered.wait(10)
                with pytest.raises(AgentTaskError, match='active transfer'):
                    runtime.close()
                with pytest.raises(AgentTaskError, match='another runtime'):
                    AgentRuntime(runtime.store.path, targets={'local-files': FileTarget()})
            finally:
                release.set()
            assert future.result(timeout=10)['state'] == 'active'


def test_closed_controller_refuses_before_reopening_any_store(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, _task, _output, _body, _users):
        controller = runtime.transfers
        runtime.close()
        def forbidden(*_args, **_kwargs):
            raise AssertionError('a closed source may not reopen its store')
        monkeypatch.setattr(runtime.store, 'connection', forbidden)
        with pytest.raises(AgentTaskError, match='closed'):
            controller.peer('export', {'export_id': 'a' * 32})


def test_distinct_runtime_database_names_cannot_clean_each_others_private_accounts(tmp_path):
    first = PrivateTransferCache(str(tmp_path / 'service.sqlite3'))
    second = PrivateTransferCache(str(tmp_path / 'service.db'))
    account = 'a' * 32
    first.store.put_chunk(account, sha256(b'first').hexdigest(), b'first')
    second.store.put_chunk(account, sha256(b'second').hexdigest(), b'second')
    first.delete_account(account)
    assert second.store.read_chunk(account, sha256(b'second').hexdigest()) == b'second'
