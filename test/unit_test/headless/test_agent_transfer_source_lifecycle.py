"""Real source recovery bounds, current historical principals and durable export lifecycle."""
from contextlib import contextmanager
from concurrent.futures import CancelledError
from hashlib import sha256
from dataclasses import asdict
import json
import os
from types import SimpleNamespace
from pathlib import Path
from uuid import uuid4

import pytest

from headless.test_agent_transfer_source import completed_source, create_for, review_for
from headless.test_agent_transfer_source_lineage import recovered_file_node, recover_nodes
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.file_target import FileTarget
from je_auto_control.utils.agent_runtime import transfer_source
from je_auto_control.utils.agent_runtime import transfer_records
from je_auto_control.utils.agent_runtime import transfer_files
from je_auto_control.utils.agent_runtime.task_authority import ownership_review
from je_auto_control.utils.exception.cancellation import CancellationToken, cancellation_scope
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@contextmanager
def reviewed_recovery(tmp_path, *, private_output=False):
    owners = UserStore(tmp_path / 'owners.json')
    owners.add_user(user_id='owner', display_name='Owner', role='operator')
    reviewers = UserStore(tmp_path / 'reviewers.json')
    reviewers.add_user(user_id='reviewer', display_name='Reviewer', role='admin')
    owner = AuthorizationContext('owner', 'operator', store_path=str(owners.path))
    actor = AuthorizationContext('reviewer', 'admin', store_path=str(reviewers.path))
    config = {'actor': actor, 'source_owner': True}
    with authorization_scope(owner):
        with recovered_file_node(tmp_path, recovery_config=config,
                                 output_path=reviewers.path if private_output else None) as values:
            runtime, source, child, output, body, batch = values
            yield runtime, source, child, output, body, batch, owners, reviewers


def test_actual_explicit_recovery_reviewers_store_is_private_before_export(tmp_path):
    with reviewed_recovery(tmp_path, private_output=True) as values:
        runtime, _source, child, *_rest = values
        with pytest.raises(AgentTaskError, match='private'):
            review_for(runtime, child)


@pytest.mark.parametrize('lost', ['owner', 'reviewer'])
@pytest.mark.parametrize('boundary', ['review', 'create', 'export', 'chunk'])
def test_actual_ancestor_owner_and_explicit_reviewer_revocation_invalidates_export(tmp_path, lost, boundary):
    with reviewed_recovery(tmp_path) as values:
        runtime, _source, child, _output, _body, _batch, owners, reviewers = values
        review = review_for(runtime, child) if boundary != 'review' else None
        exported = create_for(runtime, review) if boundary in {'export', 'chunk'} else None
        (owners if lost == 'owner' else reviewers).remove_user(lost)
        with pytest.raises(AgentTaskError):
            if boundary == 'review':
                review_for(runtime, child)
            elif boundary == 'create':
                create_for(runtime, review)
            else:
                request = {'export_id': exported['export_id']}
                if boundary == 'chunk':
                    request['sha256'] = exported['manifest']['files'][0]['chunks'][0]
                runtime.transfers.peer(boundary, request)


@pytest.mark.parametrize('depth', [16, 17])
def test_actual_recovery_chain_obeys_the_sixteen_link_artifact_boundary(tmp_path, depth):
    with recovered_file_node(tmp_path, recovery_config={'depth': depth}) as values:
        runtime, _source, child, _output, _body, _batch = values
        with runtime.store.connection() as connection:
            assert connection.execute('SELECT COUNT(*) FROM agent_task_recoveries').fetchone()[0] == depth
        if depth == 16:
            exported = create_for(runtime, review_for(runtime, child))
            assert runtime.transfers.peer('export', {'export_id': exported['export_id']})['source_task'] == child
        else:
            with pytest.raises(AgentTaskError, match='sixteen'):
                review_for(runtime, child)


@pytest.mark.parametrize('boundary', ['review', 'create', 'chunk'])
def test_cancelled_source_operation_does_not_continue_to_read_or_issue(tmp_path, boundary):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        review = review_for(runtime, task) if boundary != 'review' else None
        exported = create_for(runtime, review) if boundary == 'chunk' else None
        token = CancellationToken(1)
        token.cancel()
        with cancellation_scope(token), pytest.raises(CancelledError):
            if boundary == 'review':
                review_for(runtime, task)
            elif boundary == 'create':
                create_for(runtime, review)
            else:
                runtime.transfers.peer('chunk', {'export_id': exported['export_id'],
                    'sha256': exported['manifest']['files'][0]['chunks'][0]})


@pytest.mark.parametrize('boundary', ['reserve', 'consume_review'])
def test_actual_cancellation_after_source_sql_rolls_back_readability_and_releases_owned_bytes(
        tmp_path, monkeypatch, boundary):
    with completed_source(tmp_path) as (runtime, task, output, body, _users):
        review = review_for(runtime, task)
        source = runtime.transfers.source
        original = getattr(source.records, boundary)
        token = CancellationToken(2)
        def cancelled(*args, **kwargs):
            result = original(*args, **kwargs)
            token.cancel()
            return result
        monkeypatch.setattr(source.records, boundary, cancelled)
        with cancellation_scope(token), pytest.raises(CancelledError):
            create_for(runtime, review)
        with runtime.store.connection() as connection:
            rows = source.records.entries(connection, 'export')
        assert len(rows) == (0 if boundary == 'reserve' else 1)
        assert all(row['state'] == 'revoked' and not row['held'] for row in rows)
        with source._cache.store._database.connection() as connection:
            assert connection.execute('SELECT COUNT(*) FROM sync_asset_chunks').fetchone()[0] == 0
        assert output.read_bytes() == body


def test_expired_unconsumed_review_cannot_create_a_persistent_reservation(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        review = review_for(runtime, task)
        monkeypatch.setattr(transfer_source, 'time', SimpleNamespace(time=lambda: review['review_expires']))
        with pytest.raises(AgentTaskError, match='expired'):
            create_for(runtime, review)
        with runtime.store.connection() as connection:
            assert runtime.transfers.source.records.entries(connection, 'export') == []


@pytest.mark.parametrize('recovery', [False, True])
def test_actual_restart_preserves_exact_bytes_grant_and_original_expiry(tmp_path, recovery):
    context = recovered_file_node(tmp_path) if recovery else completed_source(tmp_path)
    with context as values:
        runtime = values[0]
        task, output, body = (values[2], values[3], values[4]) if recovery else values[1:4]
        review = review_for(runtime, task)
        exported = create_for(runtime, review)
        path = runtime.store.path
        runtime.close()
        output.write_bytes(b'later user output does not rewrite the consented artifact')
        reopened = AgentRuntime(path, targets={'local-files': FileTarget()})
        try:
            assert create_for(reopened, review) == exported
            manifest = reopened.transfers.peer('export', {'export_id': exported['export_id']})
            assert manifest == exported['manifest']
            chunk = reopened.transfers.peer('chunk', {'export_id': exported['export_id'],
                'sha256': manifest['files'][0]['chunks'][0]})
            assert chunk['sha256'] == sha256(body).hexdigest()
        finally:
            reopened.close()


def test_failed_owned_cache_cleanup_keeps_revocation_and_capacity_until_confirmed_retry(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, output, body, _users):
        exported = create_for(runtime, review_for(runtime, task))
        source = runtime.transfers.source
        original = source._cache.delete_account
        def failed(_account):
            raise OSError('owned test cleanup failure')
        monkeypatch.setattr(source._cache, 'delete_account', failed)
        request = {'export_id': exported['export_id']}
        with pytest.raises(AgentTaskError):
            runtime.transfers.control('revoke_export', request)
        with runtime.store.connection() as connection:
            retained = source.records.find(connection, exported['export_id'])
        assert retained['state'] == 'revoked' and retained['held']
        with pytest.raises(AgentTaskError):
            runtime.transfers.peer('export', request)
        monkeypatch.setattr(source._cache, 'delete_account', original)
        revoked = runtime.transfers.control('revoke_export', request)['export']
        assert revoked['state'] == 'revoked' and not revoked['cleanup_pending']
        assert output.read_bytes() == body


@pytest.mark.parametrize('accepted_key', [None, 'actual-standalone-original'])
def test_genuine_standalone_recovery_uses_actual_optional_requests_without_fabricated_dag(tmp_path, accepted_key):
    with completed_source(tmp_path) as (runtime, _initial, output, body, _users):
        action = {'tool': 'AC_workflow_manifest', 'arguments': {'directory': str(tmp_path),
            'path': str(tmp_path / 'standalone-manifest.json'), 'names': [output.name]}}
        source = runtime.submit({'goal': 'standalone actual reviewed file action', 'target': 'local-files',
            'mode': 'skill', 'roots': [str(tmp_path)], 'allowed_tools': ['AC_workflow_manifest'], 'actions': [action],
            'success_criteria': [{'kind': 'file_sha256', 'path': str(output), 'value': sha256(body).hexdigest()},
                                 {'kind': 'actions_complete'}]}, idempotency_key=accepted_key)
        runtime.pause(source.task_id)
        child = recover_nodes(runtime, source.task_id, {})
        exported = create_for(runtime, review_for(runtime, child))
        assert exported['manifest']['files'][0]['sha256'] == sha256(body).hexdigest()
        with runtime.store.connection() as connection:
            assert connection.execute('SELECT COUNT(*) FROM agent_dag_local_tasks').fetchone()[0] == 0
            assert connection.execute('SELECT COUNT(*) FROM agent_task_submissions').fetchone()[0] == 0


def test_artifact_expiry_uses_its_actual_completed_source_not_an_older_terminal_ancestor(tmp_path):
    with recovered_file_node(tmp_path, recovery_config={'ancestor_age': 120}) as values:
        runtime, source, child, *_rest = values
        with runtime.store.connection() as connection:
            ancestor = runtime.store.read_task(connection, source)
            leaf = runtime.store.read_task(connection, child)
        assert ancestor['state'] == 'cancelled' and leaf['updated'] - ancestor['updated'] >= 120
        exported = create_for(runtime, review_for(runtime, child))
        assert exported['manifest']['expires'] == leaf['updated'] + 30 * 86400


@pytest.mark.parametrize('boundary', ['review', 'export'])
def test_actual_cyclic_recovery_relation_is_refused_without_unbounded_traversal(tmp_path, boundary):
    with recovered_file_node(tmp_path) as (runtime, _source, child, _output, _body, _batch):
        exported = create_for(runtime, review_for(runtime, child)) if boundary == 'export' else None
        with runtime.store.connection(write=True) as connection:
            connection.execute('UPDATE agent_task_recoveries SET source_task=? WHERE task_id=?', (child, child))
        with pytest.raises(AgentTaskError, match='cyclic'):
            if boundary == 'review':
                review_for(runtime, child)
            else:
                runtime.transfers.peer('export', {'export_id': exported['export_id']})


@pytest.mark.parametrize('boundary', ['create', 'export'])
def test_valid_replacement_of_actual_private_reviewer_still_requires_new_export_consent(tmp_path, boundary):
    with reviewed_recovery(tmp_path) as values:
        runtime, _source, child, _output, _body, _batch, _owners, reviewers = values
        reviewers.add_user(user_id='alternate', display_name='Alternate reviewer', role='admin')
        review = review_for(runtime, child)
        exported = create_for(runtime, review) if boundary == 'export' else None
        with runtime.store.connection(write=True) as connection:
            encoded = connection.execute('SELECT details FROM agent_recovery_owners WHERE task_id=?',
                                         (child,)).fetchone()[0]
            details = json.loads(encoded)
            details['actor'] = asdict(AuthorizationContext('alternate', 'admin', store_path=str(reviewers.path)))
            replacement = ownership_review({key: value for key, value in details.items()
                                           if key not in {'review', 'source_snapshot'}}, details['source_snapshot'])
            connection.execute('UPDATE agent_recovery_owners SET details=? WHERE task_id=?',
                               (json.dumps(replacement), child))
        with pytest.raises(AgentTaskError, match='changed'):
            if boundary == 'create':
                create_for(runtime, review)
            else:
                runtime.transfers.peer('export', {'export_id': exported['export_id']})


def test_expired_grant_never_reads_surviving_private_cached_bytes(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        exported = create_for(runtime, review_for(runtime, task))
        source = runtime.transfers.source
        with source._cache.store._database.connection() as connection:
            assert connection.execute('SELECT COUNT(*) FROM sync_asset_chunks').fetchone()[0] > 0
        def forbidden(*_args, **_kwargs):
            raise AssertionError('expired grant may not read surviving cached bytes')
        monkeypatch.setattr(source._cache.store, 'read_chunk', forbidden)
        monkeypatch.setattr(transfer_records, 'time', SimpleNamespace(time=lambda: exported['manifest']['expires']))
        with pytest.raises(AgentTaskError, match='not active'):
            runtime.transfers.peer('chunk', {'export_id': exported['export_id'],
                'sha256': exported['manifest']['files'][0]['chunks'][0]})


def test_cancelled_reply_after_real_grant_commit_recovers_exact_intent_without_a_second_account(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        review = review_for(runtime, task)
        source = runtime.transfers.source
        original = source._create
        token = CancellationToken(3)
        def lost_reply(*args, **kwargs):
            result = original(*args, **kwargs)
            token.cancel()
            return result
        monkeypatch.setattr(source, '_create', lost_reply)
        with cancellation_scope(token), pytest.raises(CancelledError):
            create_for(runtime, review)
        with runtime.store.connection() as connection:
            committed = source.records.entries(connection, 'export')
        assert len(committed) == 1 and committed[0]['state'] == 'active'
        recovered = create_for(runtime, review)
        assert recovered['export_id'] == committed[0]['id']
        with runtime.store.connection() as connection:
            assert source.records.entries(connection, 'export') == committed


@pytest.mark.parametrize('boundary', ['create', 'export'])
def test_actual_linked_source_directory_cannot_read_an_unrelated_out_of_scope_file(tmp_path, monkeypatch, boundary):
    directory = tmp_path / 'source'
    directory.mkdir()
    output = directory / 'result.txt'
    body = b'actual owned source directory output'
    output.write_bytes(body)
    with recovered_file_node(tmp_path, recover=False, output_path=output) as values:
        runtime, _source, task, *_rest = values
        review = review_for(runtime, task)
        exported = create_for(runtime, review) if boundary == 'export' else None
        outside_directory = tmp_path.parent / (uuid4().hex + '-unrelated')
        outside_directory.mkdir()
        outside = outside_directory / output.name
        outside.write_bytes(body)
        assert directory.resolve().is_relative_to(tmp_path.resolve())
        assert outside_directory.resolve().is_relative_to(tmp_path.parent.resolve())
        output.unlink()
        directory.rmdir()
        if os.name == 'nt':
            from _winapi import CreateJunction
            CreateJunction(str(outside_directory), str(directory))
        else:
            directory.symlink_to(outside_directory, target_is_directory=True)
        assert directory.resolve() == outside_directory.resolve()
        original = transfer_files.os.open
        def confined(value, *args, **kwargs):
            if Path(value).resolve() == outside.resolve():
                raise AssertionError('the unrelated target descriptor must never be opened')
            return original(value, *args, **kwargs)
        monkeypatch.setattr(transfer_files.os, 'open', confined)
        try:
            with pytest.raises(AgentTaskError):
                if boundary == 'create':
                    create_for(runtime, review)
                else:
                    runtime.transfers.peer('export', {'export_id': exported['export_id']})
            assert outside.read_bytes() == body
        finally:
            if os.name == 'nt':
                directory.rmdir()
            else:
                directory.unlink()
