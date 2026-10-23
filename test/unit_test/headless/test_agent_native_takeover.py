"""Physical presence notices cancel and retire a fake native helper across IPC."""
import sys
import time

from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget

HELPER = '''
import json, sys, time
for line in sys.stdin.buffer:
    request=json.loads(line)
    operation=request['operation']
    if operation=='bootstrap': result={'protocol':1}
    elif operation=='configure': result={'ready':True}
    elif operation=='observe': result={'identity':'fixture'}
    elif operation=='perform':
        print(json.dumps({'control':'physical_input'}),flush=True)
        time.sleep(30)
        result=True
    else: result=True
    print(json.dumps({'id':request['id'],'result':result}),flush=True)
'''


def test_physical_notice_pauses_owned_task_and_reaps_blocked_helper(tmp_path):
    from concurrent.futures import CancelledError
    import pytest
    adapter = NativeDesktopTarget(argv=[sys.executable, "-u", "-c", HELPER], resource_path=tmp_path / "input.lock")
    runtime = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": adapter})
    try:
        task = runtime.submit({"goal": "fixture", "target": "fixture", "allowed_tools": ["AC_fixture"],
            "success_criteria": [{"kind": "result_equals", "key": "ok", "value": True}]})
        frame = runtime.observe(task.task_id)
        with pytest.raises(CancelledError):
            runtime.act(task.task_id, {"tool": "AC_fixture", "observation_id": frame.observation_id})
        deadline = time.monotonic() + 3
        while runtime.get(task.task_id).state == "pausing" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.get(task.task_id).state == "paused"
        assert not runtime._leases
        assert adapter._channel is None
        assert adapter._ledger.empty
    finally:
        runtime.close()
