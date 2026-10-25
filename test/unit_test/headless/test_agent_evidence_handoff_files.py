"""Actual file helpers and permanent read-only completion cross callers only through reviewed evidence."""
from contextlib import ExitStack
from types import SimpleNamespace
import json

import pytest

from headless.test_agent_evidence_handoff import perform, grant_for
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@pytest.fixture
def files(tmp_path):
    users = UserStore(tmp_path / 'users.json')
    users.add_user(user_id='owner', display_name='Owner', role='operator')
    users.add_user(user_id='reviewer', display_name='Reviewer', role='admin')
    owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
    reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
    document = tmp_path / 'result.txt'
    document.write_text('complete', encoding='utf-8')
    manifest = tmp_path / 'manifest.json'
    action = {'tool': 'AC_workflow_manifest', 'arguments': {
        'directory': str(tmp_path), 'path': str(manifest), 'names': ['result.txt']}}
    spec = {'goal': 'Verify the actual owned-file workflow', 'target': 'local-files', 'mode': 'skill',
            'roots': [str(tmp_path)], 'allowed_tools': ['AC_workflow_manifest'], 'actions': [action],
            'success_criteria': [{'kind': 'actions_complete'}, {'kind': 'file_exists', 'path': str(manifest)},
                                 {'kind': 'file_text', 'path': str(document), 'value': 'complete'}]}
    target = NativeDesktopTarget(resource_path=tmp_path / 'owned-input.lock')
    runtime = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'local-files': target})
    runtime.background = SimpleNamespace(start=lambda _task_id: None)
    definition = {'nodes': [{'id': 'a', 'host': 'local', 'task': {
        'spec': spec, 'idempotency_key': 'owned-file-evidence-handoff', 'wait_seconds': 20}}]}
    scopes = ExitStack()
    scopes.enter_context(authorization_scope(owner))
    try:
        batch = runtime.batches.control('register', {'definition': definition})
        with authorization_scope(reviewer):
            started = runtime.batches.control('begin', {'batch_id': batch['batch_id'],
                                                       'definition': definition, 'max_parallel': 4})
            claim = {'batch_id': batch['batch_id'], 'attempt': started['attempt'], 'node_id': 'a'}
            runtime.batches.control('claim', claim)
            task = started['definition']['nodes'][0]['task']
            source = runtime.batches.control('local_task', {**claim, 'operation': 'submit', 'body': {
                'spec': task['spec'], 'idempotency_key': task['idempotency_key']}})['task_id']
            perform(runtime, source, action)
            runtime.pause(source)
            runtime.batches.control('pause_batch', {'batch_id': batch['batch_id']})
            preview = runtime.recovery.control('preview_completion', {'task_id': source})
            child = runtime.recovery.control('create_completion', {'task_id': source,
                'snapshot': preview['snapshot'], 'note': 'Verify retired original file effects only'})['task_id']
            assert runtime.finish(child).state == 'succeeded'
        yield SimpleNamespace(runtime=runtime, owner=owner, reviewer=reviewer, users=users, source=source,
                              child=child, batch_id=batch['batch_id'], definition=definition,
                              target=target, manifest=manifest)
    finally:
        with authorization_scope(None):
            runtime.close()
        scopes.close()


def test_real_file_handoff_runs_the_original_dag_without_replaying_or_transferring_task_ownership(files,
                                                                                                monkeypatch, tmp_path):
    from je_auto_control.utils.rest_api.rest_server import RestApiServer
    from je_auto_control.utils.dag import run_dag
    before = files.manifest.read_bytes()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Handoff and DAG adoption must not probe or replay the original file helper')
    for name in ('ready', 'observe', 'perform'):
        monkeypatch.setattr(files.target, name, forbidden)
    grant = grant_for(files)
    server = RestApiServer(port=0, token='owned-native-file-handoff', agent_runtime=files.runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = tmp_path / 'connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': server.token,
                                          'generation': 'owned-native-file-handoff'}), encoding='utf-8')
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path', lambda: connection)
        decision = {'node_id': 'a', 'action': 'successor', 'task_id': files.child, 'handoff_id': grant['id']}
        review = files.runtime.batches.control('review_continuation', {'batch_id': files.batch_id,
            'definition': files.definition, 'decisions': [decision]})
        approved = {key: review[key] for key in ('batch_id', 'definition', 'snapshot', 'decisions')}
        result = run_dag(files.definition, batch_id=files.batch_id,
                         recovery={**approved, 'note': 'Approve only the exact handed-off final verification'})
        assert result.succeeded, result.to_dict()
        assert files.runtime.get(files.source).state == 'paused'
        assert files.runtime.store.get(files.child)['owner']['user_id'] == 'reviewer'
        with pytest.raises(AgentTaskError, match='another caller'):
            files.runtime.get(files.child)
        assert files.manifest.read_bytes() == before and files.runtime.store.actions(files.child) == []
    finally:
        server.stop()
