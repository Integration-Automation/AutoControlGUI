"""Independent public runs isolate variables; nested helpers use their owner."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from je_auto_control.utils.executor import action_executor as module


def test_top_level_vars_do_not_leak():
    first = module.execute_action_with_vars([["AC_get_var", {"name": "private"}]], {"private": "first"})
    second = module.execute_action([["AC_set_var", {"name": "copy", "value": "${private}"}]])
    assert list(first.values()) == ["first"]
    assert any("Unknown variable" in str(value) for value in second.values())


def test_parallel_nested_helpers_use_branch_scope(monkeypatch):
    barrier = Barrier(2)
    captured = []

    def nested_read():
        barrier.wait(timeout=5)
        result = module.execute_action_with_vars([["AC_get_var", {"name": "branch"}]], {})
        captured.extend(result.values())

    monkeypatch.setitem(module.executor.event_dict, "AC_scope_read", nested_read)
    branches = [
        [["AC_set_var", {"name": "branch", "value": value}], ["AC_scope_read"]]
        for value in ("left", "right")
    ]
    module.execute_action([["AC_parallel", {"branches": branches}]])
    assert sorted(captured) == ["left", "right"]


def test_concurrent_public_runs_keep_separate_seed_values(monkeypatch):
    barrier = Barrier(2)

    def nested_read():
        barrier.wait(timeout=5)
        return next(iter(module.execute_action([["AC_get_var", {"name": "value"}]]).values()))

    monkeypatch.setitem(module.executor.event_dict, "AC_scope_read", nested_read)

    def run(value):
        return next(iter(module.execute_action_with_vars([["AC_scope_read"]], {"value": value}).values()))

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, ["left", "right"])) == ["left", "right"]


def test_explicit_execution_scope_restores_after_exception():
    from je_auto_control.utils.script_vars.scope import execution_scope

    with execution_scope({"outer": "kept"}) as outer:
        with pytest.raises(RuntimeError):
            with execution_scope({"nested": "shared"}) as nested:
                assert outer is nested
                raise RuntimeError("unwind")
        assert outer["nested"] == "shared"
        assert list(module.execute_action([["AC_get_var", {"name": "outer"}]]).values()) == ["kept"]
    with execution_scope() as after:
        assert not after


def test_parallel_branches_inherit_seed_without_mutating_parent():
    from je_auto_control.utils.script_vars.scope import execution_scope

    with execution_scope({"seed": "original"}) as parent:
        result = module.execute_action([["AC_parallel", {"branches": [
            [["AC_get_var", {"name": "seed"}], ["AC_set_var", {"name": "seed", "value": "changed"}]],
        ]}]])
        parallel = next(iter(result.values()))
        assert list(parallel["results"][0].values())[0] == "original"
        assert parent["seed"] == "original"


def test_dag_workers_inherit_public_seed_and_branch_commands(monkeypatch):
    captured = []

    def read_seed():
        captured.append(module._running_executor().variables.get_value("seed"))

    monkeypatch.setitem(module.executor.event_dict, "AC_scope_read", read_seed)
    result = module.execute_action_with_vars([["AC_run_dag", {"definition": {"nodes": [
        {"id": "one", "actions": [["AC_scope_read"]]},
        {"id": "two", "actions": [["AC_scope_read"]]},
    ]}}]], {"seed": "parent"})
    assert next(iter(result.values()))["succeeded"] is True
    assert captured == ["parent", "parent"]


def test_branch_mutating_nested_variable_does_not_change_parent(monkeypatch):
    from je_auto_control.utils.script_vars.scope import execution_scope

    def mutate():
        module._running_executor().variables["config"]["values"].append("branch")

    monkeypatch.setitem(module.executor.event_dict, "AC_scope_mutate", mutate)
    with execution_scope({"config": {"values": ["parent"]}}) as scope:
        module.execute_action([["AC_parallel", {"branches": [[["AC_scope_mutate"]]]}]])
        assert scope["config"] == {"values": ["parent"]}


def test_explicit_scope_is_exported_from_the_public_facade():
    import je_auto_control as ac
    assert "execution_scope" in ac.__all__
    with ac.execution_scope({"seed": "public"}):
        assert list(ac.execute_action([["AC_get_var", {"name": "seed"}]]).values()) == ["public"]


def test_strict_rest_runs_are_isolated():
    from je_auto_control.utils.rest_api.rest_handlers import _execute_strict
    first, _ = _execute_strict([["AC_set_var", {"name": "rest_private", "value": "first"}]])
    second, response = _execute_strict([["AC_set_var", {"name": "copy", "value": "${rest_private}"}]])
    assert first == 200
    assert second == 200
    assert response["ok"] is False


def test_worker_scope_forks_an_inherited_context():
    from je_auto_control.utils.script_vars.scope import execution_scope
    with execution_scope({"values": ["parent"]}) as parent:
        with execution_scope(parent, isolated=True) as child:
            child["values"].append("child")
            assert parent["values"] == ["parent"]
        assert module.executor.variables is parent


def test_mcp_request_does_not_inherit_host_variables():
    from je_auto_control.utils.mcp_server.tools._handlers_runs import execute_actions
    from je_auto_control.utils.script_vars.scope import execution_scope
    with execution_scope({"host_private": "host"}):
        result = execute_actions([["AC_set_var", {"name": "copy", "value": "${host_private}"}]])
    assert any("Unknown variable" in value for value in result.values())
