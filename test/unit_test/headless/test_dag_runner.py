"""Tests for the cross-host DAG orchestrator."""
import json
import threading
import time

import pytest

from je_auto_control.utils.dag import (
    DagDefinition, DagDefinitionError, DagNode, STATUS_FAILED,
    STATUS_SKIPPED, STATUS_SUCCEEDED, parse_dag, run_dag,
)


# === graph parsing ==========================================================

def test_node_rejects_empty_id():
    with pytest.raises(DagDefinitionError):
        DagNode(id="", actions=[])


def test_node_rejects_no_payload():
    with pytest.raises(DagDefinitionError):
        DagNode(id="a")


def test_node_rejects_both_payloads():
    with pytest.raises(DagDefinitionError):
        DagNode(id="a", actions=[], action_file="x.json")


def test_definition_detects_duplicate_ids():
    with pytest.raises(DagDefinitionError, match="duplicate"):
        DagDefinition(nodes=(
            DagNode(id="a", actions=[]),
            DagNode(id="a", actions=[]),
        ))


def test_definition_detects_unknown_dependency():
    with pytest.raises(DagDefinitionError, match="unknown"):
        DagDefinition(nodes=(
            DagNode(id="a", actions=[], depends_on=("missing",)),
        ))


def test_topological_order_diamond():
    dag = DagDefinition(nodes=(
        DagNode(id="root", actions=[]),
        DagNode(id="left", actions=[], depends_on=("root",)),
        DagNode(id="right", actions=[], depends_on=("root",)),
        DagNode(id="join", actions=[], depends_on=("left", "right")),
    ))
    order = dag.topological_order()
    assert order.index("root") == 0
    assert order.index("join") == len(order) - 1
    assert order.index("left") < order.index("join")
    assert order.index("right") < order.index("join")


def test_topological_order_detects_cycle():
    dag = DagDefinition.__new__(DagDefinition)
    # Bypass __post_init__ to construct a cycle for the topo path test.
    object.__setattr__(dag, "nodes", (
        DagNode(id="a", actions=[], depends_on=()),
        DagNode(id="b", actions=[], depends_on=("a",)),
    ))
    # Use a fresh, mutating depends-on dict to bypass validation.
    a = DagNode(id="a", actions=[])
    b = DagNode(id="b", actions=[], depends_on=("a",))
    # Force a → b → a by swapping nodes in a definition whose
    # post-init runs but where we manually edit dependencies after.
    dag = DagDefinition(nodes=(a, b))
    object.__setattr__(dag.nodes[0], "depends_on", ("b",))
    with pytest.raises(DagDefinitionError, match="cycle"):
        dag.topological_order()


def test_parse_dag_round_trips_basic_definition():
    raw = {
        "nodes": [
            {"id": "a", "actions": []},
            {"id": "b", "host": "machine-1",
             "action_file": "x.json", "depends_on": ["a"]},
        ],
    }
    dag = parse_dag(raw)
    by_id = dag.by_id()
    assert by_id["a"].host == "local"
    assert by_id["b"].host == "machine-1"
    assert by_id["b"].action_file == "x.json"
    assert by_id["b"].depends_on == ("a",)


def test_parse_dag_rejects_empty_nodes():
    with pytest.raises(DagDefinitionError):
        parse_dag({"nodes": []})


# === runner =================================================================

def _local_runner_recording(calls, fail_ids=None):
    def runner(node, _dag):
        calls.append(node.id)
        if fail_ids and node.id in fail_ids:
            raise RuntimeError(f"forced failure on {node.id}")
        return {"ran": node.id}
    return runner


def test_run_dag_executes_in_topological_order_local():
    calls: list = []
    raw = {
        "nodes": [
            {"id": "root", "actions": []},
            {"id": "child", "actions": [], "depends_on": ["root"]},
        ],
    }
    result = run_dag(
        raw, max_parallel=1,
        local_runner=_local_runner_recording(calls),
    )
    assert result.succeeded is True
    assert calls == ["root", "child"]
    assert result.nodes["root"].status == STATUS_SUCCEEDED
    assert result.nodes["child"].status == STATUS_SUCCEEDED


def test_run_dag_marks_downstream_skipped_on_failure():
    raw = {
        "nodes": [
            {"id": "root", "actions": []},
            {"id": "mid", "actions": [], "depends_on": ["root"]},
            {"id": "leaf", "actions": [], "depends_on": ["mid"]},
        ],
    }
    result = run_dag(
        raw, max_parallel=1,
        local_runner=_local_runner_recording([], fail_ids={"root"}),
    )
    assert result.succeeded is False
    assert result.nodes["root"].status == STATUS_FAILED
    assert result.nodes["mid"].status == STATUS_SKIPPED
    assert result.nodes["leaf"].status == STATUS_SKIPPED


def test_run_dag_independent_branch_runs_when_other_fails():
    raw = {
        "nodes": [
            {"id": "fail_root", "actions": []},
            {"id": "child", "actions": [], "depends_on": ["fail_root"]},
            {"id": "indep", "actions": []},
        ],
    }
    calls: list = []
    result = run_dag(
        raw, max_parallel=2,
        local_runner=_local_runner_recording(calls, fail_ids={"fail_root"}),
    )
    assert result.nodes["fail_root"].status == STATUS_FAILED
    assert result.nodes["child"].status == STATUS_SKIPPED
    assert result.nodes["indep"].status == STATUS_SUCCEEDED


def test_run_dag_uses_remote_runner_for_non_local_host():
    raw = {
        "nodes": [{"id": "remote_step", "host": "machine-a", "actions": []}],
    }
    remote_calls: list = []

    def remote(node, _dag):
        remote_calls.append(node.id)
        return {"remote_ran": node.id}

    local_calls: list = []
    result = run_dag(
        raw, max_parallel=1,
        local_runner=_local_runner_recording(local_calls),
        remote_runner=remote,
    )
    assert local_calls == []
    assert remote_calls == ["remote_step"]
    assert result.nodes["remote_step"].status == STATUS_SUCCEEDED


def test_run_dag_parallel_diamond_runs_branches_concurrently():
    raw = {
        "nodes": [
            {"id": "root", "actions": []},
            {"id": "a", "actions": [], "depends_on": ["root"]},
            {"id": "b", "actions": [], "depends_on": ["root"]},
            {"id": "join", "actions": [], "depends_on": ["a", "b"]},
        ],
    }
    overlap = {"max_parallel": 0}
    counter_lock = threading.Lock()
    counter = {"active": 0}

    def runner(node, _dag):
        with counter_lock:
            counter["active"] += 1
            overlap["max_parallel"] = max(
                overlap["max_parallel"], counter["active"],
            )
        time.sleep(0.05)
        with counter_lock:
            counter["active"] -= 1
        return node.id

    result = run_dag(raw, max_parallel=4, local_runner=runner)
    assert result.succeeded is True
    assert overlap["max_parallel"] >= 2  # a + b should overlap


def test_run_dag_result_serialises_to_dict():
    raw = {"nodes": [{"id": "only", "actions": []}]}
    result = run_dag(
        raw, max_parallel=1,
        local_runner=_local_runner_recording([]),
    )
    data = result.to_dict()
    assert data["succeeded"] is True
    assert data["nodes"]["only"]["status"] == STATUS_SUCCEEDED
    assert "duration_ms" in data["nodes"]["only"]


def test_run_dag_accepts_existing_definition():
    dag = DagDefinition(nodes=(DagNode(id="only", actions=[]),))
    result = run_dag(
        dag, max_parallel=1,
        local_runner=_local_runner_recording([]),
    )
    assert result.succeeded is True


# === executor / MCP / façade wiring ========================================

def test_executor_registers_run_dag():
    from je_auto_control.utils.executor.action_executor import executor
    assert "AC_run_dag" in executor.known_commands()


def test_mcp_factory_registers_run_dag_tool():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_run_dag" in names


def test_facade_exports_dag_api():
    import je_auto_control as ac
    for name in ("DagDefinition", "DagNode", "DagRunResult",
                  "parse_dag", "run_dag"):
        assert hasattr(ac, name)


def test_definition_round_trips_through_json():
    raw = {
        "nodes": [
            {"id": "a", "actions": [["AC_screenshot", {}]]},
            {"id": "b", "action_file": "x.json", "depends_on": ["a"]},
        ],
    }
    dag = parse_dag(raw)
    # Re-encode and re-parse to confirm the schema is stable.
    encoded = json.dumps({
        "nodes": [{
            "id": n.id, "host": n.host,
            "actions": n.actions, "action_file": n.action_file,
            "depends_on": list(n.depends_on),
        } for n in dag.nodes],
    })
    reparsed = parse_dag(json.loads(encoded))
    assert {n.id for n in reparsed.nodes} == {"a", "b"}
