"""External/local-model recovery requires an explicit new goal and fresh execution evidence."""
from copy import deepcopy
from unittest.mock import Mock
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.agent_runtime.routes import dispatch
from je_auto_control.utils.agent_runtime.jobs import BackgroundTasks
from .test_agent_runtime import FakeTarget, specification


@pytest.fixture(params=["external", "ollama"])
def dynamic_source(tmp_path, request):
    target = FakeTarget()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": target})
    mode = request.param
    options = {"model": "fixture-tools", "endpoint": "http://127.0.0.1:11434"} if mode == "ollama" else {}
    source = runtime.submit(specification(mode=mode, actions=[], options=options,
        success_criteria=[{"kind": "result_equals", "key": "value", "value": 3}]))
    frame = runtime.observe(source.task_id)
    runtime.act(source.task_id, {"tool": "AC_increment", "arguments": {"amount": 1},
                                "observation_id": frame.observation_id})
    runtime.pause(source.task_id)
    yield runtime, target, source.task_id, mode
    runtime.close()


def proposal(runtime, source):
    view = runtime.recovery.control("preview", {"task_id": source})
    spec = deepcopy(view["review_template"])
    spec["goal"] = "Perform only the remaining increment of two, then independently verify three"
    return {"task_id": source, "snapshot": view["snapshot"], "spec": spec,
            "note": "Reviewed the completed increment and the current application state"}


def test_preview_does_not_invent_remaining_actions_or_contact_a_model(dynamic_source, monkeypatch):
    runtime, target, source, mode = dynamic_source
    before = runtime.store.get(source), runtime.receipts(source)
    network = Mock(side_effect=AssertionError("preview contacted a model"))
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.ollama.request_json", network)
    view = runtime.recovery.control("preview", {"task_id": source})
    assert view["source_mode"] == mode and view["draft"] is None
    assert view["completed_steps"] is None and view["attempted_steps"] == 1
    assert view["remaining_actions"] == [] and view["rows"] == []
    assert view["issues"] == ["new_plan_required"]
    template = view["review_template"]
    assert template["goal"] == "" and template["mode"] == mode and template["actions"] == []
    assert template["options"] == runtime.store.get(source)["spec"]["options"]
    assert target.calls == ["AC_increment"]
    assert (runtime.store.get(source), runtime.receipts(source)) == before
    network.assert_not_called()


def test_reviewed_dynamic_successor_starts_with_fresh_history_and_completion(dynamic_source):
    runtime, target, source, mode = dynamic_source
    request = proposal(runtime, source)
    child = runtime.recovery.control("create", request)["task_id"]
    assert runtime.store.actions(child) == []
    if mode == "external":
        frame = runtime.observe(child)
        runtime.act(child, {"tool": "AC_increment", "arguments": {"amount": 2},
                            "observation_id": frame.observation_id})
        assert runtime.finish(child).state == "succeeded"
    else:
        histories = []

        class Model:
            def decide(self, _observation, history, **_kwargs):
                histories.append(list(history))
                return ({"tool": "AC_increment", "arguments": {"amount": 2}}
                        if not history else {"stop": True})

        assert run_task(runtime, child, backend=Model()).state == "succeeded"
        assert histories[0] == [] and len(histories[1]) == 1
    assert len(target.calls) == 2 and runtime.get(source).state == "paused"
    assert runtime.get(child).metadata["recovery"]["source_task"] == source
    assert runtime.recovery.control("create", request)["task_id"] == child
    with pytest.raises(AgentTaskError, match="reviewed successor"):
        runtime.resume(source)


@pytest.mark.parametrize("change", [
    "blank", "dormant_actions", "mode", "model", "endpoint",
])
def test_dynamic_approval_requires_a_new_goal_without_switching_execution_authority(dynamic_source, change):
    runtime, _target, source, mode = dynamic_source
    request = proposal(runtime, source)
    if change == "blank":
        request["spec"]["goal"] = ""
    elif change == "dormant_actions":
        request["spec"]["actions"] = [{"tool": "AC_increment"}]
    elif change == "mode":
        request["spec"]["mode"] = "skill"
    elif change == "model":
        request["spec"]["options"]["model"] = "different-model"
    else:
        request["spec"]["options"]["endpoint"] = "http://unapproved.invalid"
    with pytest.raises(AgentTaskError):
        runtime.recovery.control("create", request)
    assert len(runtime.list()) == 1 and runtime.get(source).state == "paused"


def test_explicit_approval_can_retain_goal_wording_without_inheriting_source_progress(dynamic_source):
    runtime, _target, source, _mode = dynamic_source
    request = proposal(runtime, source)
    request["spec"]["goal"] = runtime.store.get(source)["spec"]["goal"]
    request["note"] = "Reviewed the same overall goal with a new application context and no receipt inheritance"
    child = runtime.recovery.control("create", request)["task_id"]
    assert runtime.store.actions(child) == []
    assert runtime.get(child).state == "queued" and runtime.get(source).state == "paused"


def test_new_dynamic_goal_is_not_accepted_while_source_effects_are_unknown(dynamic_source):
    runtime, _target, source, _mode = dynamic_source
    action = runtime.store.actions(source)[0]
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_actions SET status='uncertain' WHERE id=?", (action["id"],))
    request = proposal(runtime, source)
    with pytest.raises(AgentTaskError, match="reconcile unknown"):
        runtime.recovery.control("create", request)
    runtime.reconcile(source, {"action_id": action["id"], "decision": "applied", "result": {"value": 1},
                              "note": "Independently confirmed the first increment"})
    with pytest.raises(AgentTaskError, match="snapshot changed"):
        runtime.recovery.control("create", request)
    request = proposal(runtime, source)
    assert runtime.recovery.control("create", request)["state"] == "queued"


def test_dormant_dynamic_action_arrays_do_not_claim_finite_progress(dynamic_source):
    runtime, _target, source, _mode = dynamic_source
    data = runtime.store.get(source)["spec"]
    data["actions"] = [{"tool": "AC_increment", "arguments": {"amount": 99}, "row": "unexecuted-plan"}]
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET spec=? WHERE id=?", (json.dumps(data), source))
    view = runtime.recovery.control("preview", {"task_id": source})
    assert view["completed_steps"] is None and view["rows"] == [] and view["remaining_actions"] == []
    assert view["review_template"]["actions"] == []


def test_finish_without_new_results_cannot_inherit_a_matching_source_result(dynamic_source):
    runtime, target, source, mode = dynamic_source
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_actions SET result=? WHERE task_id=?", ('{"value":3}', source))
    target.value = 3
    child = runtime.recovery.control("create", proposal(runtime, source))["task_id"]
    if mode == "ollama":
        stop = Mock(decide=Mock(return_value={"stop": True}))
        result = run_task(runtime, child, backend=stop)
    else:
        result = runtime.finish(child)
    assert result.state == "waiting_user" and result.verification[0]["status"] == "unknown"
    assert runtime.store.actions(child) == []
    assert runtime.store.actions(source)[0]["result"] == {"value": 3}


class ModelHandler(BaseHTTPRequestHandler):
    """A test-owned Ollama-compatible endpoint; no actual model is selected or installed."""

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append((self.path, body))
        if self.path == "/api/show":
            value = {"capabilities": ["tools"]}
        elif len([path for path, _ in self.server.calls if path == "/api/chat"]) == 1:
            value = {"message": {"tool_calls": [{"function": {"name": "AC_workflow_control", "arguments": {
                "operation": "get", "selector": {"name": "remaining-field"}}}}]}}
        else:
            value = {"message": {"content": "done", "tool_calls": []}}
        payload = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


def test_explicit_local_replan_uses_the_pinned_http_model_with_fresh_goal_and_history(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
    server.calls = []
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    jobs = BackgroundTasks(runtime)
    runtime.background = jobs
    try:
        source = runtime.submit(specification(mode="ollama", allowed_tools=["AC_workflow_control"], options={
            "model": "fixture-tools", "endpoint": f"http://127.0.0.1:{server.server_port}"},
            success_criteria=[{"kind": "result_equals", "key": "value", "value": 2}]))
        frame = runtime.observe(source.task_id)
        runtime.act(source.task_id, {"tool": "AC_workflow_control", "arguments": {"operation": "get",
            "selector": {"name": "first-field"}}, "observation_id": frame.observation_id})
        runtime.pause(source.task_id)
        view = dispatch(runtime, "recovery", {"operation": "preview", "request": {"task_id": source.task_id}})
        assert server.calls == []
        reviewed = view["review_template"]
        reviewed["goal"] = "Read only the remaining field and verify the final result"
        child = dispatch(runtime, "recovery", {"operation": "create", "request": {"task_id": source.task_id,
            "snapshot": view["snapshot"], "spec": reviewed, "note": "Reviewed current field state"}})["task_id"]
        deadline = time.monotonic() + 5
        while runtime.get(child).state in {"queued", "running", "verifying"} and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.get(child).state == "succeeded"
        assert [path for path, _ in server.calls] == ["/api/show", "/api/chat", "/api/chat"]
        assert all(body["model"] == "fixture-tools" for _, body in server.calls)
        first = json.loads(server.calls[1][1]["messages"][1]["content"])
        second = json.loads(server.calls[2][1]["messages"][1]["content"])
        assert first["goal"] == reviewed["goal"] and first["recent_results"] == []
        assert len(second["recent_results"]) == 1
        assert len(runtime.store.actions(child)) == 1 and len(runtime.store.actions(source.task_id)) == 1
        assert runtime.get(source.task_id).state == "paused"
    finally:
        jobs.close()
        runtime.background = None
        runtime.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
