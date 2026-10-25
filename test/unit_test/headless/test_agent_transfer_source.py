"""Actual completed file tasks export only explicitly consented immutable outcomes."""
import base64
from contextlib import contextmanager
from hashlib import sha256
import json
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.file_target import FileTarget
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@contextmanager
def completed_source(tmp_path, *, kind='file_sha256', named=False, inputs=None):
    body = 'original 已驗證的成果'.encode('utf-8')
    output = tmp_path / 'report.txt'
    output.write_bytes(body)
    users = UserStore(tmp_path / 'users.json') if named else None
    if users:
        for user, role in [('owner', 'operator'), ('reviewer', 'admin'), ('other', 'operator')]:
            users.add_user(user_id=user, display_name=user, role=role)
    owner = AuthorizationContext('owner', 'operator', store_path=str(users.path)) if users else None
    clause = {'kind': kind, 'path': str(output)}
    if kind == 'file_sha256':
        clause['value'] = sha256(body).hexdigest()
    elif kind == 'file_text':
        clause['value'] = '已驗證'
    elif kind == 'file_exists':
        clause['min_bytes'] = len(body)
    runtime = AgentRuntime(tmp_path / 'runtime.sqlite3', targets={'local-files': FileTarget()})
    try:
        with authorization_scope(owner):
            task = runtime.submit({'goal': 'verify owned output', 'target': 'local-files',
                                   'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(tmp_path)],
                                   'inputs': {} if inputs is None else inputs,
                                   'success_criteria': [clause]})
            assert runtime.finish(task.task_id).state == 'succeeded'
        yield runtime, task.task_id, output, body, users
    finally:
        runtime.close()


def review_for(runtime, task, *, policy='caller', names=None):
    return runtime.transfers.control('review_export', {'source_task': task,
        'selection': [{'criterion': 0, 'names': [] if names is None else names}],
        'recipient_policy': policy, 'idempotency_key': 'approved-export'})


def create_for(runtime, review):
    return runtime.transfers.control('create_export', {'review': review['review'],
        'note': 'Explicitly approve only these selected bytes', 'idempotency_key': 'approved-export'})['export']


def test_completed_file_requires_review_then_exports_real_immutable_bytes(tmp_path):
    body = b'original verified output'
    output = tmp_path / 'report.txt'
    output.write_bytes(body)
    runtime = AgentRuntime(tmp_path / 'runtime.sqlite3', targets={'local-files': FileTarget()})
    try:
        task = runtime.submit({'goal': 'verify this owned output', 'target': 'local-files',
                               'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(tmp_path)],
                               'success_criteria': [{'kind': 'file_sha256', 'path': str(output),
                                                     'value': sha256(body).hexdigest()}]})
        finished = runtime.finish(task.task_id)
        assert finished.state == 'succeeded'
        assert finished.metadata['completion_contract'] == 1
        assert finished.metadata['input_released'] is True
        assert hasattr(runtime, 'transfers'), 'runtime-owned source transfer controller is not implemented'
        review = runtime.transfers.control('review_export', {
            'source_task': task.task_id, 'selection': [{'criterion': 0, 'names': []}],
            'recipient_policy': 'caller', 'idempotency_key': 'reviewed-source-export'})
        assert review['approval_required'] is True
        assert review['manifest']['files'][0]['sha256'] == sha256(body).hexdigest()
        assert str(tmp_path) not in str(review)
        request = {'review': review['review'], 'note': 'Approve exactly these output bytes',
                   'idempotency_key': 'reviewed-source-export'}
        created = runtime.transfers.control('create_export', request)['export']
        again = runtime.transfers.control('create_export', request)['export']
        assert created == again
        manifest = runtime.transfers.peer('export', {'export_id': created['export_id']})
        assert manifest == review['manifest']
        digest = manifest['files'][0]['chunks'][0]
        reply = runtime.transfers.peer('chunk', {'export_id': created['export_id'], 'sha256': digest})
        assert reply == {'contract': 1, 'sha256': digest, 'data': base64.b64encode(body).decode('ascii')}
        output.write_bytes(b'later user edits do not mutate the historical exported artifact')
        assert runtime.transfers.peer('export', {'export_id': created['export_id']}) == manifest
        assert runtime.transfers.peer('chunk', {'export_id': created['export_id'], 'sha256': digest}) == reply
    finally:
        runtime.close()


def test_text_criterion_exports_actual_utf8_bytes(tmp_path):
    with completed_source(tmp_path, kind='file_text') as (runtime, task, _output, body, _users):
        created = create_for(runtime, review_for(runtime, task))
        assert created['manifest']['files'][0]['sha256'] == sha256(body).hexdigest()


@pytest.mark.parametrize('missing_unselected', [False, True])
@pytest.mark.parametrize('long_receipt_name', [False, True])
def test_manifest_subset_uses_original_names_and_verified_real_manifest_entries(
        tmp_path, missing_unselected, long_receipt_name):
    first, second = tmp_path / 'one.txt', tmp_path / 'two.txt'
    first.write_bytes(b'first')
    second.write_bytes(b'second')
    manifest_path = tmp_path / ('m' * 150 + '.json' if long_receipt_name else 'manifest.json')
    manifest_path.write_text(json.dumps({'files': [
        {'name': path.name, 'path': str(path), 'bytes': path.stat().st_size,
         'sha256': sha256(path.read_bytes()).hexdigest()}
        for path in (first, second)]}), encoding='utf-8')
    runtime = AgentRuntime(tmp_path / 'runtime.sqlite3', targets={'local-files': FileTarget()})
    try:
        task = runtime.submit({'goal': 'verify manifest', 'target': 'local-files', 'roots': [str(tmp_path)],
            'allowed_tools': ['AC_workflow_manifest'], 'success_criteria': [{'kind': 'file_manifest',
            'path': str(manifest_path), 'directory': str(tmp_path), 'names': [first.name, second.name]}]})
        assert runtime.finish(task.task_id).state == 'succeeded'
        if missing_unselected:
            first.unlink()
        created = create_for(runtime, review_for(runtime, task.task_id, names=[second.name]))
        assert [item['name'] for item in created['manifest']['files']] == [second.name]
    finally:
        runtime.close()


def test_changed_exists_output_must_still_satisfy_its_original_minimum(tmp_path):
    with completed_source(tmp_path, kind='file_exists') as (runtime, task, output, _body, _users):
        output.write_bytes(b'x')
        with pytest.raises(AgentTaskError):
            review_for(runtime, task)


def test_review_hashing_has_an_actual_deadline_before_authority_can_be_issued(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        source = runtime.transfers.source
        original = source._scan
        clock = [0.0]
        monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
        def delayed(*args, **kwargs):
            clock[0] = 31.0
            return original(*args, **kwargs)
        monkeypatch.setattr(source, '_scan', delayed)
        with pytest.raises(AgentTaskError, match='deadline'):
            review_for(runtime, task)


@pytest.mark.parametrize(('policy', 'recipient'), [('caller', 'reviewer'), ('source_owner', 'owner')])
def test_named_source_recipient_is_derived_from_real_local_account(tmp_path, policy, recipient):
    with completed_source(tmp_path, named=True) as (runtime, task, _output, body, users):
        reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
        with authorization_scope(reviewer):
            created = create_for(runtime, review_for(runtime, task, policy=policy))
        with authorization_scope(AuthorizationContext(recipient, 'operator', store_path=str(users.path))):
            manifest = runtime.transfers.peer('export', {'export_id': created['export_id']})
            assert manifest['files'][0]['sha256'] == sha256(body).hexdigest()
        with authorization_scope(AuthorizationContext('other', 'operator', store_path=str(users.path))):
            with pytest.raises(AgentTaskError):
                runtime.transfers.peer('export', {'export_id': created['export_id']})


@pytest.mark.parametrize('lost', ['owner', 'reviewer'])
def test_live_source_owner_and_issuer_revocation_invalidate_peer_reads(tmp_path, lost):
    with completed_source(tmp_path, named=True) as (runtime, task, _output, _body, users):
        reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
        with authorization_scope(reviewer):
            created = create_for(runtime, review_for(runtime, task, policy='source_owner'))
        users.remove_user(lost)
        with authorization_scope(AuthorizationContext('owner', 'operator', store_path=str(users.path))):
            with pytest.raises(AgentTaskError):
                runtime.transfers.peer('export', {'export_id': created['export_id']})


def test_source_bytes_changed_after_review_never_publish_and_user_file_is_preserved(tmp_path):
    with completed_source(tmp_path) as (runtime, task, output, _body, _users):
        review = review_for(runtime, task)
        output.write_bytes(b'changed after review')
        with pytest.raises(AgentTaskError):
            create_for(runtime, review)
        assert output.read_bytes() == b'changed after review'
        with runtime.store.connection() as connection:
            rows = runtime.transfers.source.records.entries(connection, 'export')
        assert len(rows) == 1 and rows[0]['state'] == 'revoked' and rows[0]['held'] is False


@pytest.mark.parametrize('operation', [[], {}])
def test_untyped_operation_is_rejected_by_the_boundary(tmp_path, operation):
    with completed_source(tmp_path) as (runtime, _task, _output, _body, _users):
        with pytest.raises(AgentTaskError):
            runtime.transfers.control(operation, {})


@pytest.mark.parametrize('operation', [[], {}])
def test_untyped_peer_operation_is_rejected_by_the_boundary(tmp_path, operation):
    with completed_source(tmp_path) as (runtime, _task, _output, _body, _users):
        with pytest.raises(AgentTaskError):
            runtime.transfers.peer(operation, {})


def test_large_original_task_inputs_do_not_replace_the_small_transfer_manifest_budget(tmp_path):
    with completed_source(tmp_path, inputs={'padding': '中' * 230_000}) as value:
        runtime, task, _output, body, _users = value
        created = create_for(runtime, review_for(runtime, task))
        assert created['state'] == 'active'
        assert created['manifest']['files'][0]['sha256'] == sha256(body).hexdigest()
        assert 'padding' not in str(created)


def test_source_file_changed_after_grant_write_never_becomes_a_readable_export(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, output, _body, _users):
        review = review_for(runtime, task)
        records = runtime.transfers.source.records
        original = records.consume_review
        def changed(connection, *args):
            result = original(connection, *args)
            output.write_bytes(b'edited while the grant transaction is still open')
            return result
        monkeypatch.setattr(records, 'consume_review', changed)
        with pytest.raises(AgentTaskError):
            create_for(runtime, review)
        with pytest.raises(AgentTaskError):
            runtime.transfers.peer('export', {'export_id': review['manifest']['export_id']})
        assert output.read_bytes() == b'edited while the grant transaction is still open'
