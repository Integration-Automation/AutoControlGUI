"""Reserved stop admission never bypasses live identity, ownership or closed operation validation."""
import json

import pytest

from headless.test_agent_control_priority import exhaust_polling, request, server as _server
from headless.test_agent_dag_batches import graph
from headless.test_agent_runtime_service import spec
from headless.test_rest_auth_compatibility import LegacyGate
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.delegation import HEADER, sign_principal
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore
from je_auto_control.utils.rest_api.rest_auth import RestAuthGate

server = _server


def test_wrong_bearer_cannot_pause_after_polling_limit(server):
    instance, runtime = server
    task = runtime.submit(spec())
    exhaust_polling(instance)
    assert request(instance, '/agent/pause', {'task_id': task.task_id}, token='wrong')[0] == 401
    assert runtime.get(task.task_id).state == 'queued'
    assert 'autocontrol_rest_failed_auth_total 1' in instance._metrics.render()


@pytest.mark.parametrize('change,status', [('foreign_owner', 409), ('viewer', 403), ('removed', 401)])
def test_live_forwarded_authority_remains_required_for_reserved_control(server, tmp_path, change, status):
    instance, runtime = server
    users = UserStore(tmp_path / 'users.json')
    users.add_user(user_id='alice', display_name='Alice', role='operator')
    users.add_user(user_id='bob', display_name='Bob', role='operator')
    owner = AuthorizationContext('alice', 'operator', store_path=str(users.path))
    with authorization_scope(owner):
        task = runtime.submit(spec())
    caller = AuthorizationContext('bob', 'operator', store_path=str(users.path)) if change == 'foreign_owner' else owner
    signature = sign_principal(caller, instance.token, '/agent/pause')
    if change == 'viewer':
        users.set_role('alice', 'viewer')
    if change == 'removed':
        users.remove_user('alice')
    exhaust_polling(instance)
    assert request(instance, '/agent/pause', {'task_id': task.task_id}, headers={HEADER: signature})[0] == status
    assert runtime.store.get(task.task_id)['state'] == 'queued'


def test_custom_gate_keeps_its_refusal_on_control_route(server):
    instance, runtime = server
    task = runtime.submit(spec())
    gate = LegacyGate('rate_limited')
    instance._server.auth_gate = gate
    assert request(instance, '/agent/pause', {'task_id': task.task_id})[0] == 429
    assert runtime.get(task.task_id).state == 'queued'


@pytest.mark.parametrize('body', [[], {'operation': 'local_task', 'request': {'operation': 'submit'}},
                                 {'operation': 'pause_batch', 'request': {'batch_id': 'x'}, 'extra': True}])
def test_malformed_marked_dag_cannot_run(server, body):
    instance, runtime = server
    exhaust_polling(instance)
    assert request(instance, '/agent/dag', body, headers={'X-AutoControl-Agent-Control': '1'})[0] == 400
    assert runtime.list() == []


def test_marker_on_submit_cannot_borrow_stop_reserve(server):
    instance, runtime = server
    exhaust_polling(instance)
    assert request(instance, '/agent/submit', {'spec': spec()},
                   headers={'X-AutoControl-Agent-Control': '1'})[0] == 429
    assert runtime.list() == []


def test_client_batch_pause_uses_transport_and_server_stop_reserves(server, tmp_path):
    from je_auto_control.utils.agent_runtime import transport
    instance, runtime = server
    batch = runtime.batches.control('register', {'definition': graph()})
    connection = tmp_path / 'connection.json'
    connection.write_text(json.dumps({'url': instance.base_url, 'token': instance.token}), encoding='utf-8')
    exhaust_polling(instance)
    acquired = []
    try:
        for _ in range(4):
            assert transport._SLOTS.acquire(blocking=False)
            acquired.append(True)
        result = AgentRuntimeClient(connection).call('dag', {
            'operation': 'pause_batch', 'request': {'batch_id': batch['batch_id']}})
        assert result['state'] == 'waiting_review'
    finally:
        for _ in acquired:
            transport._SLOTS.release()


def test_both_admission_lanes_resolve_store_tokens_live(tmp_path):
    users = UserStore(tmp_path / 'tokens.json')
    token = users.add_user(user_id='operator', display_name='Operator', role='operator')
    gate = RestAuthGate('inactive-shared', user_store=users, requests_per_minute=0, burst=4)
    header = f'Bearer {token}'
    normal = gate.authenticate(client_ip='192.0.2.1', header_value=header)
    control = gate.authenticate(client_ip='192.0.2.1', header_value=header, control=True)
    assert normal.verdict == control.verdict == 'ok'
    assert normal.context.user_id == control.context.user_id == 'operator'
    users.rotate_token('operator')
    assert gate.authenticate(client_ip='192.0.2.1', header_value=header, control=True).verdict == 'unauthorized'
    assert gate.authenticate(client_ip='192.0.2.1', header_value='Bearer inactive-shared',
                              control=True).verdict == 'unauthorized'


def test_control_bucket_is_per_ip_and_refills_without_refilling_polling(monkeypatch):
    from types import SimpleNamespace
    from je_auto_control.utils.rest_api import rest_auth
    current = [0.0]
    monkeypatch.setattr(rest_auth, 'time', SimpleNamespace(monotonic=lambda: current[0]))
    gate = RestAuthGate('fixture', requests_per_minute=60, burst=1)
    def authenticate(ip='192.0.2.1', control=False):
        return gate.authenticate(client_ip=ip, header_value='Bearer fixture', control=control).verdict
    assert authenticate() == authenticate(control=True) == 'ok'
    assert authenticate() == authenticate(control=True) == 'rate_limited'
    assert authenticate('192.0.2.2', True) == 'ok'
    current[0] = 1.0
    assert authenticate() == 'ok'
    assert authenticate(control=True) == 'ok'
    assert authenticate() == 'rate_limited'
