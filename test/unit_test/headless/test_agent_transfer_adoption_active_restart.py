"""Cold coordinator revocation preserves real in-flight file effects and unknown pause retirement."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Event

import pytest

from headless.test_agent_transfer_adoption import review_adoption, approve, start, revoke
from headless.test_agent_transfer_evidence_remote import remote_recovery, grant
from headless.test_agent_transfer_peer_security import post
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.dag import managed_tasks
from je_auto_control.utils.rbac.authorization import authorization_scope


def admitted(value, reviewed, running):
    value.coordinator.batches.control('claim', {'batch_id': reviewed['batch_id'],
        'attempt': running['attempt'], 'node_id': 'downstream'})
    task = next(node['task'] for node in running['definition']['nodes'] if node['id'] == 'downstream')
    status, accepted = post(value.server, '/agent/submit', {key: task[key]
        for key in ('spec', 'idempotency_key')}, token=value.owner_token)
    assert status == 200, accepted
    unrelated = deepcopy(task['spec'])
    unrelated['options'].pop('dag_batch')
    status, independent = post(value.server, '/agent/submit', {'spec': unrelated,
        'idempotency_key': 'independent-cold-adoption-task'}, token=value.owner_token)
    assert status == 200, independent
    return task, accepted['task_id'], independent['task_id']


@pytest.mark.parametrize('lost_pause_ack', [False, True])
def test_cold_coordinator_pauses_only_owned_inflight_effect_and_never_attests_uncertain_retirement(
        tmp_path, monkeypatch, lost_pause_ack):
    with remote_recovery(tmp_path, monkeypatch, dependent=True) as value:
        identifier = grant(value)
        reviewed = review_adoption(value, identifier)
        running = start(value, reviewed, approve(value, reviewed))
        task, dependent, independent = admitted(value, reviewed, running)
        previous = value.runtime.store.get(independent)['state']
        target = value.runtime._targets['local-files']
        perform = target.perform
        entered, release = Event(), Event()
        calls = []
        def held(name, arguments):
            result = perform(name, arguments)
            calls.append(name)
            entered.set()
            assert release.wait(10)
            return result
        monkeypatch.setattr(target, 'perform', held)
        action = task['spec']['actions'][0]
        def execute():
            with authorization_scope(value.owner):
                frame = value.runtime.observe(dependent)
                return value.runtime.act(dependent, {**action, 'observation_id': frame.observation_id})
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(execute)
            try:
                assert entered.wait(5)
                effect = Path(action['arguments']['path'])
                original_bytes = effect.read_bytes()
                if lost_pause_ack:
                    original = managed_tasks.bound_task_connection
                    def connection(host, binding):
                        call = original(host, binding)
                        def response(operation, body, timeout):
                            result = call(operation, body, timeout)
                            if operation == 'pause':
                                raise OSError('Owned pause accepted; acknowledgement intentionally lost')
                            return result
                        return response
                    monkeypatch.setattr(managed_tasks, 'bound_task_connection', connection)
                revoke(value, identifier)
                with pytest.raises(AgentTaskError):
                    value.coordinator.batches.control('validate_node', {'batch_id': reviewed['batch_id'],
                        'attempt': running['attempt'], 'node_id': 'remote-file'})
                path = value.coordinator.store.path
                value.coordinator.close()
                value.coordinator = AgentRuntime(path, targets={})
                current = value.coordinator.batches.control('get', {'batch_id': reviewed['batch_id']})
                assert current['state'] == 'waiting_review' and not future.done()
                node = next(row for row in current['nodes'] if row['id'] == 'downstream')
                assert node['phase'] == 'unknown'
                assert node['receipt'] == {'outcome': 'requires_review', 'task_id': dependent}
                with authorization_scope(value.owner):
                    stopped = value.runtime.get(dependent)
                assert stopped.state == 'pausing' and stopped.metadata['input_released'] is False
                assert value.runtime.store.get(independent)['state'] == previous
                assert effect.read_bytes() == original_bytes and calls == ['AC_workflow_manifest']
            finally:
                release.set()
                try:
                    future.result(timeout=5)
                except CancelledError:
                    pass
                value.coordinator.close()
