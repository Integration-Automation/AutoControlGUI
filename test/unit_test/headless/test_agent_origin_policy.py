"""Live path ceilings survive process boundaries and cannot be renewed by stale MCP replies."""
import json

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime import origin_policy
from je_auto_control.utils.agent_runtime.origin_policy import origin_scope
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
from .test_agent_runtime import FakeTarget, specification


@pytest.fixture(autouse=True)
def origin_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(origin_policy, "_directory", lambda: tmp_path / "origins")


def test_removed_origin_root_pauses_before_the_next_action(tmp_path):
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([tmp_path])
    identifier = policy.managed_origin()
    target = FakeTarget()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": target})
    try:
        with origin_scope(identifier):
            task = runtime.submit(specification(roots=[str(tmp_path)]))
        frame = runtime.observe(task.task_id)
        policy.set_client_roots([])
        with pytest.raises(AgentTaskError, match="origin roots changed"):
            runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
        assert target.calls == []
        assert runtime.get(task.task_id).state == "paused" and not runtime._leases
        assert "scope requires review" in runtime.get(task.task_id).reason
    finally:
        runtime.close()


def test_origin_revocation_retires_active_input_between_requests(tmp_path):
    policy = PathPolicy([tmp_path])
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        with origin_scope(policy.managed_origin()):
            task = runtime.submit(specification(roots=[str(tmp_path)]))
        runtime.observe(task.task_id)
        policy.revoke_managed_origin()
        runtime.maintain()
        assert runtime.get(task.task_id).state == "cancelled" and not runtime._leases
    finally:
        runtime.close()


def test_live_origin_survives_runtime_restart_and_task_scope_never_expands(tmp_path):
    allowed, additional = tmp_path / "allowed", tmp_path / "additional"
    allowed.mkdir()
    additional.mkdir()
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([allowed])
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    with origin_scope(policy.managed_origin()):
        task = runtime.submit(specification(roots=[str(allowed)]))
    runtime.close()
    policy.set_client_roots([allowed, additional])
    reopened = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        assert reopened.store.get(task.task_id)["spec"]["roots"] == [str(allowed.resolve())]
        assert reopened.observe(task.task_id).observation_id
        reopened.pause(task.task_id)
        policy.set_client_roots([additional])
        reopened.resume(task.task_id)
        with pytest.raises(AgentTaskError, match="origin roots changed"):
            reopened.observe(task.task_id)
    finally:
        reopened.close()


@pytest.mark.parametrize("value", ["not-an-array", [{}], [True], ["../outside"], ["a" * 32] * 17])
def test_malformed_origin_references_fail_at_submission(tmp_path, value):
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        with pytest.raises(AgentTaskError):
            runtime.submit(specification(options={"origin_policies": value}))
    finally:
        runtime.close()


def test_corrupt_or_removed_witness_does_not_become_unrestricted(tmp_path):
    policy = PathPolicy([tmp_path])
    identifier = policy.managed_origin()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        with origin_scope(identifier):
            task = runtime.submit(specification(roots=[str(tmp_path)]))
        witness = origin_policy._path(identifier)
        witness.write_text("invalid", encoding="utf-8")
        with pytest.raises(AgentTaskError, match="revoked, removed"):
            runtime.observe(task.task_id)
        witness.unlink()
        runtime.resume(task.task_id)
        with pytest.raises(AgentTaskError, match="revoked, removed"):
            runtime.observe(task.task_id)
    finally:
        runtime.close()


def test_additional_call_origin_intersects_preexisting_task_authority(tmp_path):
    allowed, other = tmp_path / "allowed", tmp_path / "other"
    allowed.mkdir()
    other.mkdir()
    original, narrower = PathPolicy([tmp_path]), PathPolicy([other])
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        with origin_scope(original.managed_origin()):
            task = runtime.submit(specification(roots=[str(allowed)]))
        with origin_scope(narrower.managed_origin()), pytest.raises(AgentTaskError, match="origin roots changed"):
            runtime.observe(task.task_id)
        assert not runtime._leases
    finally:
        runtime.close()


def test_local_client_forwards_only_restrictive_origin_over_authenticated_http(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import api
    from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
    from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([tmp_path])
    identifier = policy.managed_origin()
    service = AgentRuntimeService(tmp_path / "service", targets={"fixture": FakeTarget()})
    try:
        service.start()
        monkeypatch.setattr(api, "AgentRuntimeClient",
                            lambda: AgentRuntimeClient(tmp_path / "service/agent_runtime.json"))
        with origin_scope(identifier):
            task = api.submit_agent_task(specification(roots=[str(tmp_path)]))
        spec = service.runtime.store.get(task["task_id"])["spec"]
        assert spec["options"]["origin_policies"] == [identifier]
        policy.set_client_roots([])
        with pytest.raises(AgentTaskError, match="origin roots changed"):
            api.observe_agent_task(task["task_id"])
        assert service.runtime.get(task["task_id"]).state == "paused"
    finally:
        service.close()


def test_late_root_update_cannot_reactivate_a_retired_authority(tmp_path):
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([tmp_path])
    identifier = policy.managed_origin()
    policy.revoke_managed_origin()
    with pytest.raises(PathNotAllowedError, match="retired"):
        policy.set_client_roots([tmp_path])
    assert json.loads(origin_policy._path(identifier).read_text(encoding="utf-8"))["active"] is False


def test_nested_origin_scopes_intersect_instead_of_overriding_outer_authority(tmp_path):
    allowed, outside = tmp_path / "allowed", tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    restrictive, broad = PathPolicy([allowed]), PathPolicy([tmp_path])
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        with origin_scope(restrictive.managed_origin()), origin_scope(broad.managed_origin()):
            with pytest.raises(AgentTaskError, match="origin roots changed"):
                runtime.submit(specification(roots=[str(outside)]))
            task = runtime.submit(specification(roots=[str(allowed)]))
        assert len(runtime.store.get(task.task_id)["spec"]["options"]["origin_policies"]) == 2
    finally:
        runtime.close()


def test_legacy_mcp_tool_cannot_submit_a_task_beyond_its_path_ceiling(tmp_path):
    from je_auto_control.utils.mcp_server.tools._base import MCPTool
    from je_auto_control.utils.mcp_server.context import ToolCallContext
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        tool = MCPTool("legacy", "legacy wrapper", {"type": "object"},
                       lambda: runtime.submit(specification(roots=[str(tmp_path)])))
        context = ToolCallContext(1, path_policy=PathPolicy([allowed]))
        with pytest.raises(AgentTaskError, match="origin roots changed"):
            tool.invoke({}, ctx=context)
        assert runtime.list() == [] and origin_policy.current_origin() is None
    finally:
        runtime.close()


def test_parallel_and_custom_dag_workers_keep_legacy_mcp_origin_ceiling(tmp_path):
    from je_auto_control.utils.mcp_server.tools._base import MCPTool
    from je_auto_control.utils.mcp_server.context import ToolCallContext
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.dag.runner import run_dag
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    executor = Executor()
    executor.event_dict["AC_submit_fixture"] = lambda: runtime.submit(specification(roots=[str(tmp_path)]))
    context = ToolCallContext(1, path_policy=PathPolicy([allowed]))
    try:
        parallel = MCPTool("legacy_parallel", "parallel wrapper", {"type": "object"},
            lambda: executor.execute_one("AC_parallel", {"branches": [[["AC_submit_fixture"]]]}))
        with pytest.raises(AutoControlActionException, match="AgentTaskError.*origin roots changed"):
            parallel.invoke({}, ctx=context)
        dag = MCPTool("legacy_dag", "DAG wrapper", {"type": "object"},
            lambda: run_dag({"nodes": [{"id": "one", "actions": [["AC_submit_fixture"]]}]},
                           local_runner=lambda *_args: runtime.submit(specification(roots=[str(tmp_path)]))))
        assert not dag.invoke({}, ctx=context).succeeded
        assert runtime.list() == []
    finally:
        runtime.close()


def test_pure_tool_call_does_not_issue_managed_origin_metadata(tmp_path):
    from je_auto_control.utils.mcp_server.tools._base import MCPTool
    from je_auto_control.utils.mcp_server.context import ToolCallContext
    policy = PathPolicy([tmp_path])
    tool = MCPTool("pure", "pure tool", {"type": "object"}, lambda: 42)
    assert tool.invoke({}, ctx=ToolCallContext(1, path_policy=policy)) == 42
    assert not origin_policy._directory().exists()


def test_failed_policy_publication_invalidates_the_old_witness(tmp_path, monkeypatch):
    from je_auto_control.utils.json_store import json_store
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([tmp_path])
    identity = policy.managed_origin()

    def no_space(*_args, **_kwargs):
        raise OSError("fixture publication failure")

    monkeypatch.setattr(json_store, "atomic_write_text", no_space)
    with pytest.raises(OSError, match="publication failure"):
        policy.set_client_roots([])
    assert policy.roots() == (tmp_path.resolve(),)
    with pytest.raises(AgentTaskError, match="revoked, removed"):
        origin_policy._read(identity)
