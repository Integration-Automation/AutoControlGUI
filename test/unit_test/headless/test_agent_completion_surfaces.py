"""Real loopback/API/command and whole-DAG consumers accept only freshly verified completion successors."""
from types import SimpleNamespace
import json

import pytest

from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.dag import run_dag
from je_auto_control.utils.rest_api.rest_server import RestApiServer
from .test_agent_completion_recovery import completed as completed, child


@pytest.fixture
def connected(completed, monkeypatch, tmp_path):
    server = RestApiServer(port=0, token='owned-completion-test-token', agent_runtime=completed.runtime,
                           use_environment_users=False)
    server.start()
    path = tmp_path / 'connection.json'
    path.write_text(json.dumps({'url': server.base_url, 'token': 'owned-completion-test-token',
                                'generation': 'owned-completion-generation'}), encoding='utf-8')
    monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path', lambda: path)
    try:
        yield AgentRuntimeClient(path)
    finally:
        server.stop()


def test_python_cli_executor_mcp_and_rest_share_the_exact_reviewed_completion(connected, completed, tmp_path):
    import je_auto_control as ac
    from je_auto_control.cli import build_parser
    from je_auto_control.utils.agent_runtime.cli import run
    from je_auto_control.utils.tool_use_schema import run_tool_call
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    preview = ac.manage_agent_recovery('preview_completion', {'task_id': completed.task_id})
    path = tmp_path / 'approval.json'
    request = {'task_id': completed.task_id, 'snapshot': preview['snapshot'], 'note': 'Reviewed via public CLI'}
    path.write_text(json.dumps(request), encoding='utf-8')
    arguments = build_parser().parse_args(['agent-task', 'recovery', 'create_completion', str(path)])
    identifier = run(arguments)['task_id']
    repeated = run_tool_call('AC_agent_task_recovery', {'operation': 'create_completion', 'request': request})
    assert repeated['task_id'] == identifier
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    schema = tools['ac_agent_task_recovery'].input_schema
    assert 'preview_completion' in schema['properties']['operation']['enum']
    assert 'AC_agent_task_recovery' in COMMAND_SPECS
    result = connected.call('finish', {'task_id': identifier})
    assert result['state'] == 'succeeded'
    assert result['metadata']['completion_review']['source_task'] == completed.task_id
    assert result['metadata']['input_released'] is True


def test_fenced_dag_adopts_readonly_successor_without_replaying_the_last_action(connected, completed):
    runtime = completed.runtime
    runtime.background = SimpleNamespace(start=lambda _task_id: None)
    spec = runtime.store.get(completed.task_id)['spec']
    definition = {'nodes': [{'id': 'a', 'host': 'local', 'task': {
        'spec': spec, 'idempotency_key': 'owned-completion-dag', 'wait_seconds': 20}}]}
    batch = runtime.batches.control('register', {'definition': definition})
    started = runtime.batches.control('begin', {'batch_id': batch['batch_id'],
                                               'definition': definition, 'max_parallel': 4})
    claim = {'batch_id': batch['batch_id'], 'attempt': started['attempt'], 'node_id': 'a'}
    runtime.batches.control('claim', claim)
    task = started['definition']['nodes'][0]['task']
    source = runtime.batches.control('local_task', {**claim, 'operation': 'submit', 'body': {
        'spec': task['spec'], 'idempotency_key': task['idempotency_key']}})['task_id']
    action = spec['actions'][0]
    receipt = runtime.store.prepare(source, action['tool'], action['arguments'])
    runtime.store.settle(receipt, 'dispatched')
    runtime.store.settle(receipt, 'confirmed', {'path': str(completed.output.parent / 'manifest.json')})
    runtime.pause(source)
    runtime.batches.control('pause_batch', {'batch_id': batch['batch_id']})
    successor = child(completed, source)
    assert runtime.finish(successor).state == 'succeeded'
    review = runtime.batches.control('review_continuation', {'batch_id': batch['batch_id'], 'definition': definition,
        'decisions': [{'node_id': 'a', 'action': 'successor', 'task_id': successor}]})
    assert review['can_approve'], review
    approved = {key: review[key] for key in ('batch_id', 'definition', 'snapshot', 'decisions')}
    approved['note'] = 'Reviewed independent completion after the fenced finite action'
    result = run_dag(definition, batch_id=batch['batch_id'], recovery=approved)
    assert result.succeeded, result.to_dict()
    assert runtime.get(source).state == 'paused' and runtime.store.actions(successor) == []
