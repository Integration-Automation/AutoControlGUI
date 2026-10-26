"""Actual runtime private files never become exported artifacts merely by passing a file criterion."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from headless.test_agent_transfer_source import completed_source, create_for, review_for
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime import transfer_files
from je_auto_control.utils.agent_runtime import transfer_protocol
from je_auto_control.utils.agent_runtime.transfer_privacy import SourceFilePolicy
from je_auto_control.utils.agent_runtime.file_target import FileTarget
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore
from je_auto_control.utils.rest_api.rest_server import RestApiServer


def completed_file(runtime, root, path):
    task = runtime.submit({'goal': 'verify a selected existing file', 'target': 'local-files',
        'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(root)],
        'success_criteria': [{'kind': 'file_exists', 'path': str(path), 'min_bytes': 1}]})
    assert runtime.finish(task.task_id).state == 'succeeded'
    return task.task_id


@pytest.mark.parametrize('kind', ['users', 'runtime', 'evidence', 'cache'])
def test_actual_private_file_is_refused_before_opening_selected_bytes(tmp_path, monkeypatch, kind):
    with completed_source(tmp_path, named=True) as (runtime, initial, _output, _body, users):
        owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
        with authorization_scope(owner):
            if kind == 'cache':
                create_for(runtime, review_for(runtime, initial))
            paths = {'users': users.path, 'runtime': Path(runtime.store.path),
                     'evidence': runtime.evidence.directory(initial) / 'report.json',
                     'cache': runtime.transfers.source._cache.path}
            private = paths[kind]
            assert private.is_file() and private.stat().st_size > 0
            task = completed_file(runtime, tmp_path, private)
            actual_open = transfer_files.os.open

            def guarded_open(path, *args, **kwargs):
                if Path(path) == private:
                    raise AssertionError('selected private file reached the actual byte-open boundary')
                return actual_open(path, *args, **kwargs)

            monkeypatch.setattr(transfer_files.os, 'open', guarded_open)
            with pytest.raises(AgentTaskError, match='private'):
                review_for(runtime, task)


@pytest.mark.parametrize('name', ['users.json', 'runtime.sqlite3', 'agent_runtime.json'])
def test_user_output_with_a_private_files_basename_is_still_exportable(tmp_path, name):
    with completed_source(tmp_path, named=True) as (runtime, _initial, _output, _body, users):
        directory = tmp_path / 'user-output'
        directory.mkdir()
        output = directory / name
        body = b'explicit ordinary user output, independent of any private store'
        output.write_bytes(body)
        owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
        with authorization_scope(owner):
            task = completed_file(runtime, tmp_path, output)
            exported = create_for(runtime, review_for(runtime, task))
            assert exported['manifest']['files'] == [{'name': name, 'size': len(body),
                'sha256': sha256(body).hexdigest(), 'chunks': [sha256(body).hexdigest()]}]


@pytest.mark.parametrize('boundary', ['export', 'chunk', 'retry'])
def test_current_private_root_prevents_reading_an_older_approved_snapshot(tmp_path, boundary, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, output, _body, _users):
        review = review_for(runtime, task)
        exported = create_for(runtime, review)
        with monkeypatch.context() as scoped:
            scoped.setattr(type(runtime.evidence), 'root', property(lambda _self: output.parent))
            with pytest.raises(AgentTaskError, match='private'):
                if boundary == 'retry':
                    create_for(runtime, review)
                else:
                    request = {'export_id': exported['export_id']}
                    if boundary == 'chunk':
                        request['sha256'] = exported['manifest']['files'][0]['chunks'][0]
                    runtime.transfers.peer(boundary, request)


def test_path_authority_deadline_is_checked_before_reading_a_cached_chunk(tmp_path, monkeypatch):
    with completed_source(tmp_path) as (runtime, task, _output, _body, _users):
        exported = create_for(runtime, review_for(runtime, task))
        clock = [transfer_protocol.time.monotonic()]
        original_path = SourceFilePolicy.path

        def delayed_path(policy, value):
            result = original_path(policy, value)
            clock[0] += 31
            return result

        def forbidden_read(*_args, **_kwargs):
            raise AssertionError('a cached byte read started after the transfer deadline')

        with monkeypatch.context() as scope:
            scope.setattr(transfer_protocol.time, 'monotonic', lambda: clock[0])
            scope.setattr(SourceFilePolicy, 'path', delayed_path)
            scope.setattr(runtime.transfers.source._cache.store, 'read_chunk', forbidden_read)
            with pytest.raises(AgentTaskError, match='deadline'):
                runtime.transfers.peer('chunk', {'export_id': exported['export_id'],
                    'sha256': exported['manifest']['files'][0]['chunks'][0]})


@pytest.mark.parametrize('selected_private', [False, True])
def test_manifest_checks_only_selected_outputs_against_actual_private_sources(tmp_path, monkeypatch, selected_private):
    with completed_source(tmp_path, named=True) as (runtime, _initial, output, body, users):
        manifest = tmp_path / 'source-manifest.json'
        manifest.write_text(json.dumps({'files': [{'name': path.name, 'path': str(path),
            'bytes': path.stat().st_size, 'sha256': sha256(path.read_bytes()).hexdigest()}
            for path in (users.path, output)]}), encoding='utf-8')
        owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
        with authorization_scope(owner):
            task = runtime.submit({'goal': 'verify a real mixed manifest', 'target': 'local-files',
                'roots': [str(tmp_path)], 'allowed_tools': ['AC_workflow_manifest'],
                'success_criteria': [{'kind': 'file_manifest', 'path': str(manifest),
                                     'directory': str(tmp_path), 'names': [users.path.name, output.name]}]})
            assert runtime.finish(task.task_id).state == 'succeeded'
            actual_open = transfer_files.os.open

            def guarded_open(path, *args, **kwargs):
                if Path(path) == users.path:
                    raise AssertionError('manifest selection opened actual private user-store bytes')
                return actual_open(path, *args, **kwargs)

            monkeypatch.setattr(transfer_files.os, 'open', guarded_open)
            if selected_private:
                with pytest.raises(AgentTaskError, match='private'):
                    review_for(runtime, task.task_id, names=[users.path.name])
            else:
                exported = create_for(runtime, review_for(runtime, task.task_id, names=[output.name]))
                assert exported['manifest']['files'][0]['sha256'] == sha256(body).hexdigest()
                assert [entry['name'] for entry in exported['manifest']['files']] == [output.name]


def test_actual_service_connection_metadata_is_not_an_exportable_user_file(tmp_path, monkeypatch):
    # Disable only the external shared audit sink; service, credentials, task and stores remain real.
    monkeypatch.setattr(RestApiServer, '_open_audit_log', staticmethod(lambda: None))
    service = AgentRuntimeService(tmp_path / 'owned-service', targets={'local-files': FileTarget()})
    try:
        service.start()
        private = service.directory / 'agent_runtime.json'
        assert private.is_file()
        task = completed_file(service.runtime, service.directory, private)
        actual_open = transfer_files.os.open

        def guarded_open(path, *args, **kwargs):
            if Path(path) == private:
                raise AssertionError('source export opened the actual service credential file')
            return actual_open(path, *args, **kwargs)

        monkeypatch.setattr(transfer_files.os, 'open', guarded_open)
        with pytest.raises(AgentTaskError, match='private'):
            review_for(service.runtime, task)
    finally:
        service.close()


def test_standalone_runtime_does_not_reserve_a_guessed_connection_filename(tmp_path):
    with completed_source(tmp_path) as (runtime, _initial, _output, _body, _users):
        output = Path(runtime.store.path).with_suffix('.json')
        body = b'ordinary adjacent user output; no service owns this JSON path'
        output.write_bytes(body)
        task = completed_file(runtime, tmp_path, output)
        exported = create_for(runtime, review_for(runtime, task))
        assert exported['manifest']['files'][0]['sha256'] == sha256(body).hexdigest()


def test_actual_issuer_store_is_private_even_when_the_source_has_another_store(tmp_path, monkeypatch):
    with completed_source(tmp_path, named=True) as (runtime, _initial, _output, _body, users):
        reviewers = UserStore(tmp_path / 'actual-reviewers.json')
        reviewers.add_user(user_id='reviewer', display_name='Actual reviewer', role='admin')
        owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
        with authorization_scope(owner):
            task = completed_file(runtime, tmp_path, reviewers.path)
        issuer = AuthorizationContext('reviewer', 'admin', store_path=str(reviewers.path))
        actual_open = transfer_files.os.open

        def guarded_open(path, *args, **kwargs):
            if Path(path) == reviewers.path:
                raise AssertionError('source export opened the actual issuer user store')
            return actual_open(path, *args, **kwargs)

        monkeypatch.setattr(transfer_files.os, 'open', guarded_open)
        with authorization_scope(issuer), pytest.raises(AgentTaskError, match='private'):
            review_for(runtime, task)
