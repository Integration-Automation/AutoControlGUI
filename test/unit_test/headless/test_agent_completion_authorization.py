"""Explicit scoped renewal verifies stopped file effects without reviving original input authority."""
from contextlib import ExitStack
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, origin_policy
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@pytest.fixture
def renewal(tmp_path, monkeypatch, request):
    scopes = ExitStack()
    users = owner = reviewer = None
    kind = getattr(request, 'param', None)
    if kind in {'named', 'named_dag', 'named_dag_partial'}:
        users = UserStore(tmp_path / 'users.json')
        users.add_user(user_id='owner', display_name='Owner', role='operator')
        users.add_user(user_id='reviewer', display_name='Reviewer', role='admin')
        owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
        reviewer = AuthorizationContext('reviewer', 'admin', store_path=str(users.path))
    scopes.enter_context(authorization_scope(owner))
    allowed = tmp_path / 'allowed'
    reports = allowed / 'reports'
    reports.mkdir(parents=True)
    old = origin_policy.OriginWitness((allowed,))
    current = origin_policy.OriginWitness((reports,))
    for witness in (old, current):
        scopes.callback(origin_policy._path(witness.identifier).unlink, missing_ok=True)
    output, manifest = reports / 'result.txt', reports / 'manifest.json'
    output.write_text('complete', encoding='utf-8')
    action = {'tool': 'AC_workflow_manifest', 'arguments': {
        'directory': str(reports), 'path': str(manifest), 'names': ['result.txt']}}
    spec = {'goal': 'Renew only independent completion of original file effects',
            'target': 'local-files', 'mode': 'skill', 'roots': [str(allowed)],
            'allowed_tools': ['AC_workflow_manifest'], 'actions': [action],
            'success_criteria': [{'kind': 'actions_complete'}, {'kind': 'file_exists', 'path': str(manifest)},
                                 {'kind': 'file_text', 'path': str(output), 'value': 'complete'}]}
    if kind == 'named_dag_partial':
        final_manifest = reports / 'final-manifest.json'
        spec['actions'].append({'tool': 'AC_workflow_manifest', 'arguments': {
            'directory': str(reports), 'path': str(final_manifest), 'names': ['result.txt']}})
        spec['success_criteria'].append({'kind': 'file_exists', 'path': str(final_manifest)})
    target = NativeDesktopTarget(resource_path=tmp_path / 'owned-input.lock')
    runtime = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'local-files': target})
    try:
        with origin_policy.origin_scope(old.identifier):
            source, batch, definition = admitted(runtime, spec, kind, reviewer)
            frame = runtime.observe(source)
            runtime.act(source, {**action, 'observation_id': frame.observation_id})
            runtime.pause(source)
            if batch is not None:
                runtime.batches.control('pause_batch', {'batch_id': batch})
        if getattr(request, 'param', None) != 'active':
            old.revoke()
        def forbidden(*_args, **_kwargs):
            raise AssertionError('Renewal must never probe or replay the ordinary source helper')
        original_methods = {method: getattr(target, method) for method in ('ready', 'observe', 'perform')}
        for method in ('ready', 'observe', 'perform'):
            monkeypatch.setattr(target, method, forbidden)
        scopes.enter_context(origin_policy.origin_scope(current.identifier))
        yield SimpleNamespace(runtime=runtime, source=source, old=old, current=current,
                              allowed=allowed, reports=reports, target=target, action=action,
                              manifest=manifest, output=output, original_methods=original_methods,
                              users=users, owner=owner, reviewer=reviewer, batch_id=batch, definition=definition,
                              remaining_action=spec['actions'][-1])
    finally:
        with authorization_scope(None):
            runtime.close()
        scopes.close()


def admitted(runtime, spec, kind, reviewer):
    if kind not in {'dag', 'named_dag', 'named_dag_partial'}:
        return runtime.submit(spec).task_id, None, None
    runtime.background = SimpleNamespace(start=lambda _task_id: None)
    definition = {'nodes': [{'id': 'a', 'host': 'local', 'task': {
        'spec': spec, 'idempotency_key': 'owned-completion-renewal-dag', 'wait_seconds': 20}}]}
    batch = runtime.batches.control('register', {'definition': definition})['batch_id']
    with authorization_scope(reviewer):
        started = runtime.batches.control('begin', {'batch_id': batch, 'definition': definition, 'max_parallel': 4})
        claim = {'batch_id': batch, 'attempt': started['attempt'], 'node_id': 'a'}
        runtime.batches.control('claim', claim)
        task = started['definition']['nodes'][0]['task']
        source = runtime.batches.control('local_task', {**claim, 'operation': 'submit', 'body': {
            'spec': task['spec'], 'idempotency_key': task['idempotency_key']}})['task_id']
    return source, batch, definition


def reviewed(value, task_id=None, **fields):
    identifier = task_id or value.source
    preview = value.runtime.recovery.control('review_completion_authorization', {'task_id': identifier, **fields})
    request = {'task_id': identifier, 'snapshot': preview['snapshot'],
               'authorization_review': preview['authorization_review'],
               'note': 'Reviewed original confirmed effects under the current report-only ceiling'}
    if 'ownership' in preview:
        request.update(owner_policy='source_owner', ownership_review=preview['ownership']['review'])
    return preview, request


def create(value, task_id=None, **fields):
    _preview, request = reviewed(value, task_id, **fields)
    return value.runtime.recovery.control('create_authorized_completion', request)['task_id']


def test_explicit_renewal_finishes_real_files_without_reviving_the_original_origin(renewal):
    runtime, source = renewal.runtime, renewal.source
    historical = runtime.store.actions(source)
    revoked = origin_policy._path(renewal.old.identifier).read_bytes()
    manifest = renewal.manifest.read_bytes()
    with pytest.raises(AgentTaskError, match='managed origin'):
        runtime.recovery.control('preview_completion', {'task_id': source})
    preview, request = reviewed(renewal)
    assert preview['approval_required'] is True and preview['source_completion_inherited'] is False
    assert preview['verification_spec']['actions'] == []
    assert preview['verification_spec']['roots'] == [str(renewal.reports)]
    assert preview['authorization']['replaced_origins'] == [renewal.old.identifier]
    child = runtime.recovery.control('create_authorized_completion', request)['task_id']
    runtime.observe(child)
    result = runtime.finish(child)
    assert result.state == 'succeeded' and result.metadata['input_released'] is True
    assert result.metadata['completion_contract'] == 1
    assert [report['status'] for report in result.verification] == ['passed', 'passed', 'passed']
    assert runtime.get(source).state == 'paused' and runtime.store.actions(source) == historical
    assert runtime.store.actions(child) == [] and renewal.manifest.read_bytes() == manifest
    assert origin_policy._path(renewal.old.identifier).read_bytes() == revoked
    assert runtime.store.get(source)['spec']['roots'] == [str(renewal.allowed)]
    assert runtime.store.get(child)['spec']['roots'] == [str(renewal.reports)]
    assert runtime.recovery.control('create_authorized_completion', request)['task_id'] == child
    with pytest.raises(AgentTaskError, match='read-only'):
        runtime.recovery.control('create', {'task_id': child, 'snapshot': 'irrelevant',
            'spec': runtime.store.get(child)['spec'], 'note': 'Cannot upgrade to executable recovery'})


def test_original_effect_change_inside_admission_sql_rolls_back_the_entire_reader(renewal):
    _preview, request = reviewed(renewal)
    with renewal.runtime.store.connection(write=True) as connection:
        connection.execute("CREATE TRIGGER owned_completion_change AFTER INSERT ON agent_readonly_completions "
                           "BEGIN UPDATE agent_tasks SET reason='changed after child SQL' "
                           "WHERE id=(SELECT source_task FROM agent_task_recoveries WHERE task_id=NEW.task_id); END")
    with pytest.raises(AgentTaskError, match='changed'):
        renewal.runtime.recovery.control('create_authorized_completion', request)
    with renewal.runtime.store.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM agent_tasks').fetchone()[0] == 1
        for table in ('agent_task_recoveries', 'agent_readonly_completions', 'agent_task_authorizations'):
            assert connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    assert renewal.runtime.store.get(renewal.source)['reason'] != 'changed after child SQL'
