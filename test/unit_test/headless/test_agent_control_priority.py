"""Real authenticated stop requests retain bounded admission after ordinary polling is exhausted."""
import http.client
import json

import pytest

from headless.test_agent_runtime_service import Counter, spec
from je_auto_control.utils.agent_runtime.runtime import AgentRuntime
from je_auto_control.utils.rest_api.rest_auth import RestAuthGate
from je_auto_control.utils.rest_api.rest_server import RestApiServer


@pytest.fixture
def server(tmp_path):
    runtime = AgentRuntime(tmp_path / 'tasks.sqlite', targets={'counter': Counter(), 'fixture': Counter()})
    instance = RestApiServer(port=0, token='owned-control-fixture', enable_audit=False,
                             agent_runtime=runtime, use_environment_users=False)
    instance._auth = RestAuthGate(instance.token, requests_per_minute=0, burst=2)
    instance.start()
    try:
        yield instance, runtime
    finally:
        instance.stop()
        runtime.close()


def request(server, path, body=None, *, token='owned-control-fixture', method=None, headers=None):
    connection = http.client.HTTPConnection(*server.address, timeout=5)
    try:
        connection.request(method or ('GET' if body is None else 'POST'), path,
                           body=None if body is None else json.dumps(body),
                           headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
                                    **(headers or {})})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def exhaust_polling(server):
    assert [request(server, '/agent/tasks')[0] for _ in range(3)] == [200, 200, 429]


@pytest.mark.parametrize('operation,state', [('pause', 'paused'), ('cancel', 'cancelled')])
def test_owned_task_control_survives_exhausted_polling(server, operation, state):
    instance, runtime = server
    task = runtime.submit(spec())
    exhaust_polling(instance)
    status, result = request(instance, f'/agent/{operation}', {'task_id': task.task_id})
    assert status == 200, result
    assert result['state'] == runtime.get(task.task_id).state == state
    assert request(instance, '/agent/tasks')[0] == 429


def test_stop_all_survives_exhausted_polling(server):
    instance, runtime = server
    task = runtime.submit(spec())
    exhaust_polling(instance)
    status, result = request(instance, '/agent/stop_all', {})
    assert status == 200, result
    assert runtime.get(task.task_id).state == 'cancelled'


def test_shutdown_survives_exhausted_polling(server):
    instance, runtime = server
    exhaust_polling(instance)
    status, result = request(instance, '/agent/shutdown', {})
    assert status == 200, result
    assert runtime.shutdown_requested.is_set()


def test_control_budget_remains_bounded_and_does_not_consume_polling(server):
    instance, runtime = server
    task = runtime.submit(spec())
    results = [request(instance, '/agent/pause', {'task_id': task.task_id})[0] for _ in range(3)]
    assert results == [200, 200, 429]
    assert request(instance, '/agent/tasks')[0] == 200


@pytest.mark.parametrize('path,body', [('/agent/resume', {}), ('/agent/act', {}),
                                     ('/agent/submit', {'spec': spec()}), ('/agent/dag', {}),
                                     ('/agent/finish', {}), ('/execute', [])])
def test_ordinary_mutations_cannot_borrow_the_control_budget(server, path, body):
    instance, runtime = server
    exhaust_polling(instance)
    assert request(instance, path, body)[0] == 429
    assert runtime.list() == []


def test_batch_pause_uses_closed_control_protocol_after_polling_limit(server):
    from headless.test_agent_dag_batches import graph
    instance, runtime = server
    batch = runtime.batches.control('register', {'definition': graph()})
    exhaust_polling(instance)
    status, result = request(instance, '/agent/dag', {
        'operation': 'pause_batch', 'request': {'batch_id': batch['batch_id']}},
        headers={'X-AutoControl-Agent-Control': '1'})
    assert status == 200, result
    assert result['state'] == 'waiting_review'


@pytest.mark.parametrize('operation', ['register', 'begin', 'run_background', 'approve_continuation'])
def test_priority_header_cannot_admit_other_batch_operations(server, operation):
    instance, _runtime = server
    exhaust_polling(instance)
    status, _result = request(instance, '/agent/dag', {'operation': operation, 'request': {}},
                              headers={'X-AutoControl-Agent-Control': '1'})
    assert status == 400


def test_claimed_local_node_pause_keeps_its_admission_proof_after_polling_limit(server):
    from types import SimpleNamespace
    from headless.test_agent_dag_batches import graph
    from je_auto_control.utils.agent_runtime.dag_batch_recording import bound_node
    instance, runtime = server
    runtime.background = SimpleNamespace(start=lambda _task_id: None)
    batch = runtime.batches.control('register', {'definition': graph()})
    started = runtime.batches.control('begin', {
        'batch_id': batch['batch_id'], 'definition': graph(), 'max_parallel': 4})
    fields = {'batch_id': batch['batch_id'], 'attempt': started['attempt'], 'node_id': 'a'}
    runtime.batches.control('claim', fields)
    original = bound_node(runtime.batches._row(batch['batch_id']), 'a')['task']
    task = runtime.batches.control('local_task', {**fields, 'operation': 'submit', 'body': {
        'spec': original['spec'], 'idempotency_key': original['idempotency_key']}})
    exhaust_polling(instance)
    status, result = request(instance, '/agent/dag', {'operation': 'local_task', 'request': {
        **fields, 'operation': 'pause', 'body': {'task_id': task['task_id']}}},
        headers={'X-AutoControl-Agent-Control': '1'})
    assert status == 200, result
    assert result['state'] == runtime.get(task['task_id']).state == 'paused'
