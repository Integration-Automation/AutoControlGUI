"""Real local DAG recovery retains original admission without requiring a fabricated child submission row."""
from contextlib import contextmanager, nullcontext
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from headless.test_agent_transfer_source import create_for, review_for
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.file_target import FileTarget
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@contextmanager
def recovered_file_node(tmp_path, *, recover=True, admission_actor=None, output_path=None, recovery_config=None):
    output = tmp_path / 'public-report.txt' if output_path is None else output_path
    body = b'actual independently verified user output' if output_path is None else output.read_bytes()
    if output_path is None:
        output.write_bytes(body)
    action = {'tool': 'AC_workflow_manifest', 'arguments': {
        'directory': str(output.parent), 'path': str(tmp_path / 'reviewed-manifest.json'), 'names': [output.name]}}
    spec = {'goal': 'complete the actual reviewed file workflow', 'target': 'local-files', 'mode': 'skill',
            'roots': [str(tmp_path)], 'allowed_tools': ['AC_workflow_manifest'], 'actions': [action],
            'success_criteria': [{'kind': 'file_exists', 'path': str(output), 'min_bytes': len(body)},
                                 {'kind': 'actions_complete'}]}
    definition = {'nodes': [{'id': 'file-node', 'host': 'local', 'task': {
        'spec': spec, 'idempotency_key': 'real-file-node', 'wait_seconds': 20}}]}
    runtime = AgentRuntime(tmp_path / 'runtime.sqlite3', targets={'local-files': FileTarget()})
    runtime.background = SimpleNamespace(start=lambda _task_id: None)
    try:
        batch = runtime.batches.control('register', {'definition': definition, 'max_parallel': 1})
        started = runtime.batches.control('begin', {'batch_id': batch['batch_id'],
                                                   'definition': definition, 'max_parallel': 1})
        claim = {'batch_id': batch['batch_id'], 'attempt': started['attempt'], 'node_id': 'file-node'}
        runtime.batches.control('claim', claim)
        request = started['definition']['nodes'][0]['task']
        authority = authorization_scope(admission_actor) if admission_actor is not None else nullcontext()
        with authority:
            source = runtime.batches.control('local_task', {**claim, 'operation': 'submit', 'body': {
                'spec': request['spec'], 'idempotency_key': request['idempotency_key']}})['task_id']
        if not recover:
            assert run_task(runtime, source).state == 'succeeded'
            runtime.batches.control('pause_batch', {'batch_id': batch['batch_id']})
            yield runtime, source, source, output, body, batch['batch_id']
            return
        runtime.pause(source)
        if recovery_config and recovery_config.get('ancestor_age'):
            runtime.cancel(source)
            with runtime.store.connection(write=True) as connection:
                age = recovery_config['ancestor_age']
                connection.execute('UPDATE agent_tasks SET created=created-?,updated=updated-? WHERE id=?',
                                   (age, age, source))
        runtime.batches.control('pause_batch', {'batch_id': batch['batch_id']})
        child = recover_nodes(runtime, source, recovery_config or {})
        assert runtime.get(source).metadata['submission_contract'] == 1
        assert 'submission_contract' not in runtime.get(child).metadata
        yield runtime, source, child, output, body, batch['batch_id']
    finally:
        runtime.close()


def recover_nodes(runtime, source, config):
    actor = config.get('actor')
    authority = authorization_scope(actor) if actor is not None else nullcontext()
    with authority:
        child = source
        for _index in range(config.get('depth', 1)):
            request = {'task_id': child}
            if config.get('source_owner'):
                request['owner_policy'] = 'source_owner'
            preview = runtime.recovery.control('preview', request)
            create = {**request, 'snapshot': preview['snapshot'], 'spec': preview['draft'],
                      'note': 'Approve only the actual remaining file action'}
            if config.get('source_owner'):
                create['ownership_review'] = preview['ownership']['review']
            child = runtime.recovery.control('create', create)['task_id']
            runtime.pause(child)
        runtime.resume(child)
        assert run_task(runtime, child).state == 'succeeded'
        return child


def test_completed_real_dag_recovery_exports_with_its_original_admission(tmp_path):
    with recovered_file_node(tmp_path) as (runtime, source, child, _output, body, _batch):
        exported = create_for(runtime, review_for(runtime, child))
        manifest = runtime.transfers.peer('export', {'export_id': exported['export_id']})
        assert manifest['source_task'] == child
        assert manifest['files'][0]['sha256'] == sha256(body).hexdigest()
        assert runtime.get(source).state == 'paused'


def damage_lineage(connection, runtime, source, child, change):
    statements = {
        'submission_missing': 'DELETE FROM agent_task_submissions WHERE task_id=?',
        'submission_digest': "UPDATE agent_task_submissions SET spec_digest='changed' WHERE task_id=?",
        'request_missing': 'DELETE FROM agent_request_keys WHERE task_id=?',
        'request_digest': "UPDATE agent_request_keys SET spec_hash='changed' WHERE task_id=?",
        'admission_missing': 'DELETE FROM agent_dag_local_tasks WHERE task_id=?',
        'admission_digest': "UPDATE agent_dag_local_tasks SET spec_digest='changed' WHERE task_id=?",
    }
    if change in statements:
        connection.execute(statements[change], (source,))
    elif change == 'recovery_snapshot':
        connection.execute("UPDATE agent_task_recoveries SET snapshot='changed' WHERE task_id=?", (child,))
    else:
        row = runtime.store.read_task(connection, source)
        del row['spec']['options']['dag_batch']
        connection.execute('UPDATE agent_tasks SET spec=? WHERE id=?', (json.dumps(row['spec']), source))


@pytest.mark.parametrize('boundary', ['review', 'create', 'export', 'chunk'])
@pytest.mark.parametrize('change', ['submission_missing', 'submission_digest', 'request_missing', 'request_digest',
                                   'admission_missing', 'admission_digest', 'recovery_snapshot', 'stripped_tag'])
def test_actual_ancestor_damage_invalidates_source_at_every_boundary(tmp_path, boundary, change):
    with recovered_file_node(tmp_path) as (runtime, source, child, _output, _body, _batch):
        review = review_for(runtime, child) if boundary != 'review' else None
        exported = create_for(runtime, review) if boundary in {'export', 'chunk'} else None
        with runtime.store.connection(write=True) as connection:
            damage_lineage(connection, runtime, source, child, change)
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


@pytest.mark.parametrize('boundary', ['review', 'export'])
def test_completed_original_node_rechecks_its_actual_admitting_admin(tmp_path, boundary):
    users = UserStore(tmp_path / 'principals.json')
    users.add_user(user_id='owner', display_name='Owner', role='operator')
    users.add_user(user_id='admitting-admin', display_name='Admitting admin', role='admin')
    owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
    actor = AuthorizationContext('admitting-admin', 'admin', store_path=str(users.path))
    with authorization_scope(owner), recovered_file_node(tmp_path, recover=False, admission_actor=actor) as values:
        runtime, _source, child, _output, _body, _batch = values
        exported = create_for(runtime, review_for(runtime, child)) if boundary == 'export' else None
        users.remove_user('admitting-admin')
        with pytest.raises(AgentTaskError):
            if boundary == 'review':
                review_for(runtime, child)
            else:
                runtime.transfers.peer('export', {'export_id': exported['export_id']})


def test_actual_admitting_admin_store_is_private_even_when_its_path_differs_from_the_owner(tmp_path):
    owners = UserStore(tmp_path / 'owners.json')
    owners.add_user(user_id='owner', display_name='Owner', role='operator')
    admins = UserStore(tmp_path / 'admins.json')
    admins.add_user(user_id='admin', display_name='Admin', role='admin')
    owner = AuthorizationContext('owner', 'operator', store_path=str(owners.path))
    actor = AuthorizationContext('admin', 'admin', store_path=str(admins.path))
    with authorization_scope(owner):
        with recovered_file_node(tmp_path, recover=False, admission_actor=actor, output_path=admins.path) as values:
            runtime, _source, child, _output, _body, _batch = values
            with pytest.raises(AgentTaskError, match='private'):
                review_for(runtime, child)
