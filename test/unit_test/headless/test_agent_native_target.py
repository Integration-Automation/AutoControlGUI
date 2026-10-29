"""End-to-end owned native proxies use an IPC-only fixture instead of OS input."""
import sys

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget

HELPER = '''
import json, sys, time
counter = 0
def notify(request, event):
    print(json.dumps({'id': request['id'], 'event': event}), flush=True)
    assert json.loads(sys.stdin.buffer.readline()) == {'ack': True}
for line in sys.stdin.buffer:
    request=json.loads(line)
    operation, payload=request['operation'],request['payload']
    if operation=='bootstrap':
        result={'protocol':1}
    elif operation=='configure':
        result={'ready':True}
    elif operation=='observe':
        result={'identity':'fixture', 'value':counter}
    elif operation=='perform':
        if payload['arguments'].get('hold'):
            notify(request, {'kind':'key_press','keycode':65,'is_shift':False})
        if payload['arguments'].get('hang'):
            time.sleep(30)
        counter+=1
        result={'value':counter}
    elif operation=='cleanup':
        for key in payload['keys']:
            notify(request, {'kind':'key_release',**key})
            notify(request, {'kind':'key_released',**key})
        result={'cleaned':True}
    print(json.dumps({'id':request['id'],'result':result}),flush=True)
'''


def spec():
    return {"goal": "increment", "target": "fixture", "allowed_tools": ["AC_increment"],
            "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}],
            "budget": {"action_seconds": 1}}


def target(tmp_path):
    return NativeDesktopTarget(argv=[sys.executable, "-u", "-c", HELPER], resource_path=tmp_path / "input.lock")


def test_helper_bootstrap_has_a_separate_bound_without_extending_action_deadlines(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import native_target
    calls = []

    class Channel:
        def __init__(self, *_args, **_kwargs):
            self.retired = False

        def request(self, operation, payload, *, timeout, check, on_event=None):
            check()
            calls.append((operation, timeout))
            return {"protocol": 1} if operation == "bootstrap" else {"ready": True, "identity": "fixture"}

        def close(self):
            self.retired = True

    monkeypatch.setattr(native_target, "owned_channel", Channel)
    adapter = target(tmp_path)
    runtime = AgentRuntime(tmp_path / "one.sqlite", targets={"fixture": adapter})
    try:
        task = runtime.submit(spec())
        runtime.observe(task.task_id)
        assert calls[0] == ("bootstrap", 15)
        assert all(timeout == 1 for operation, timeout in calls if operation != "bootstrap")
    finally:
        runtime.close()


def test_pause_cleans_only_announced_input_before_retiring_helper(tmp_path):
    adapter = target(tmp_path)
    runtime = AgentRuntime(tmp_path / "one.sqlite", targets={"fixture": adapter})
    try:
        task = runtime.submit(spec())
        frame = runtime.observe(task.task_id)
        runtime.act(task.task_id, {"tool": "AC_increment", "arguments": {"hold": True},
                                   "observation_id": frame.observation_id})
        assert not adapter._ledger.empty
        assert runtime.pause(task.task_id).state == "paused"
        assert adapter._ledger.empty
        assert adapter._channel is None
    finally:
        runtime.close()


def test_hung_helper_retires_and_cleanup_replays_only_owned_releases(tmp_path):
    adapter = target(tmp_path)
    runtime = AgentRuntime(tmp_path / "one.sqlite", targets={"fixture": adapter})
    try:
        task = runtime.submit(spec())
        frame = runtime.observe(task.task_id)
        with pytest.raises(AgentTaskError, match="deadline"):
            runtime.act(task.task_id, {"tool": "AC_increment", "arguments": {"hold": True, "hang": True},
                                       "observation_id": frame.observation_id})
        assert runtime.get(task.task_id).state == "waiting_user"
        assert adapter._ledger.empty
        assert adapter._channel is None
        second = runtime.submit(spec())
        assert runtime.observe(second.task_id).observation_id
    finally:
        runtime.close()


def test_independent_databases_cannot_both_own_one_native_input_resource(tmp_path):
    first = AgentRuntime(tmp_path / "one.sqlite", targets={"fixture": target(tmp_path)})
    second = AgentRuntime(tmp_path / "two.sqlite", targets={"fixture": target(tmp_path)})
    try:
        left, right = first.submit(spec()), second.submit(spec())
        first.observe(left.task_id)
        with pytest.raises(AgentTaskError, match="owns"):
            second.observe(right.task_id)
        first.pause(left.task_id)
        assert second.observe(right.task_id).observation_id
    finally:
        first.close()
        second.close()


def test_wall_deadline_during_grounding_retires_before_input_cleanup(tmp_path):
    helper = HELPER.replace("counter = 0", "counter = 0\nobservations = 0")
    helper = helper.replace("elif operation=='observe':", "elif operation=='observe':\n"
        "        observations += 1\n        if observations == 4: time.sleep(30)")
    adapter = NativeDesktopTarget(argv=[sys.executable, "-u", "-c", helper], resource_path=tmp_path / "input.lock")
    runtime = AgentRuntime(tmp_path / "one.sqlite", targets={"fixture": adapter})
    try:
        specification = spec()
        specification["budget"] = {"wall_seconds": 2, "action_seconds": 5}
        task = runtime.submit(specification)
        frame = runtime.observe(task.task_id)
        runtime.act(task.task_id, {"tool": "AC_increment", "arguments": {"hold": True},
                                   "observation_id": frame.observation_id})
        frame = runtime.observe(task.task_id)
        with pytest.raises(AgentTaskError, match="budget"):
            runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
        assert runtime.get(task.task_id).state == "timed_out"
        assert adapter._ledger.empty
        assert adapter._channel is None
        assert not runtime._leases
    finally:
        runtime.close()
